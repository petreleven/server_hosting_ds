"""
User authentication and management routes for Quart web application.

This module provides routes for user registration, login, dashboard access,
and server management functionality.
"""

import json
import logging
from typing import Dict, Optional, List, Any
from urllib.parse import parse_qs

import asyncpg
from quart import Blueprint, current_app, redirect, render_template, request, url_for
from quart_auth import AuthUser, current_user, login_required, login_user

import helper_classes.custom_dataclass as cdata
from db import db
from game_jobs.mainProvisioner import MainProvisioner
from api_user.helpers import extract_single_sub_record

# Create logger
logger = logging.getLogger(__name__)

# Blueprint definition
userblueprint = Blueprint("userroute", __name__)

# Password hashing configuration

# TODO: Remove hardcoded secret and use environment variable
SECRET = "ygQpJHb0MNDCK0Loa1OeN.wiJH0cuiGOdZnAwW4fQlw5iqo6luZrS"


@userblueprint.route("/", methods=["GET", "POST"])
async def home():
    """
    Home page route.

    Returns:
        Home page template
    """
    return await render_template("home.html", errors={})


@userblueprint.route("/register", methods=["GET", "POST"])
async def register():
    """User registration route.

    Handles user registration by processing form data, creating a user in the database,
    and provisioning a new game server.

    Returns:
        HTML response or redirect
    """
    if request.method == "GET":
        return await render_template("home.html", errors={})

    errors = {
        "email_errors": [],
        "password_errors": [],
        "game_id_errors": [],
        "plan_id_errors": [],
        "general_errors": [],
    }
    app = current_app
    provisioner = MainProvisioner()

    req_data: bytearray = await request.body
    fields: Dict[str, List[str]] = parse_qs(req_data.decode("utf-8"))
    try:
        # Parse form data
        req_data: bytearray = await request.body
        fields: Dict[str, List[str]] = parse_qs(req_data.decode("utf-8"))

        # Validate required fields
        required_fields = ["email", "password", "game_id", "plan_id"]
        for field in required_fields:
            if field not in fields or not fields[field][0]:
                errors[f"{field}_errors"].append(f"Missing required field: {field}")
                return await render_template("home.html", errors=errors)

        # Create user data object
        data = cdata.RegisterUserData(
            email=fields["email"][0],
            password=fields["password"][0],
            game_id=fields["game_id"][0],
            plan_id=fields["plan_id"][0],
        )

        # Insert user into database
        logger.info(data)
        user_record, err = await db.db_insert_user(data)

        if not user_record:
            errors["email_errors"].append(str(err))
            logger.error(f"Failed to create user for email: {data.email}")
            return await render_template("home.html", errors=errors)

        user_id = user_record.get("id")
        if not user_id:
            errors["general_errors"].append("Invalid user data returned")
            logger.error(f"Invalid user data returned for email: {data.email}")
            return await render_template("home.html", errors=errors)

        # Authenticate the user
        login_user(AuthUser(auth_id=str(user_id)))

        # Provision server in background
        app.add_background_task(provisioner.job_order_new_trial_server, data)
        logger.info(f"User registered successfully: {data.email}")

        return redirect(url_for("userroute.dashboard"))

    except asyncpg.UniqueViolationError:
        errors["email_errors"].append("User is already registered")
        logger.warning(
            f"Registration attempt for existing email: {fields.get('email', ['<unknown>'])[0]}"
        )
        return await render_template("home.html", errors=errors)
    except Exception as e:
        errors["general_errors"].append("An unexpected error occurred")
        logger.exception(f"Exception during registration: {str(e)}")
        return await render_template("home.html", errors=errors)


@userblueprint.route("/dashboard", methods=["GET", "POST"])
@login_required
async def dashboard():
    """
    User dashboard route.

    Displays the user dashboard with their account information and servers.

    Returns:
        HTML template
    """
    return await render_template("dashboard_full.html")


@userblueprint.route("/allsubscriptions", methods=["GET", "POST"])
@login_required
async def allsubscriptions():
    """
    Dashboard servers route.

    Displays the user's servers and their status.

    Returns:
        HTML template with server data
    """
    user_id = current_user.auth_id
    if not user_id:
        logger.warning("Missing user_id in dashboardservers route")
        return await render_template("allsubscriptions.html", subscriptions=[])

    try:
        all_subs, err = await db.db_select_subscriptions_by_user(user_id=user_id)

        subscriptions = []
        for record in all_subs:
            sub = await extract_single_sub_record(record)
            if sub:  # Only append valid subscriptions
                subscriptions.append(sub)

        return await render_template(
            "allsubscriptions.html", subscriptions=subscriptions
        )
    except Exception as e:
        logger.exception(f"Error retrieving server data: {str(e)}")
        return await render_template(
            "allsubscriptions.html", subscriptions=[], error="Failed to load servers"
        )


@userblueprint.route(
    "/subscription-status/<string:subscription_id>", methods=["GET", "POST"]
)
@login_required
async def subscription_status(subscription_id: str):
    """
    Server status route.

    Displays detailed status for a specific server subscription.

    Args:
        subscription_id: ID of the subscription to display

    Returns:
        HTML template with server status
    """
    try:
        if not subscription_id:
            return await render_template(
                "single_subscription.html",
                current_sub=None,
                error="Invalid subscription ID",
            )

        record, err = await db.db_select_subscription_by_id(subscription_id)
        if not record:
            logger.warning(f"Subscription not found: {subscription_id}")
            return await render_template(
                "single_subscription.html",
                current_sub=None,
                error="Subscription not found",
            )

        current_sub = await extract_single_sub_record(record)
        return await render_template(
            "single_subscription.html", current_sub=current_sub
        )
    except Exception as e:
        logger.exception(f"Error retrieving server status: {str(e)}")
        return await render_template(
            "single_subscription.html",
            current_sub=None,
            error="Failed to load server status",
        )


@userblueprint.route("/panel", methods=["GET", "POST"])
@login_required
async def panel():
    args = request.args
    subscription_id = args.get("subscription_id")
    return await render_template("panel.html", subscription_id=subscription_id)


@userblueprint.route("/monitoring", methods=["GET"])
@login_required
async def monitoring():
    subscription_id = request.args.get("subscription_id", "")
    if not subscription_id:
        return "Missing subscription_id", 400

    # Fetch server linked to this subscription
    res = await db.db_select_server_by_subscription_id(subscription_id)
    server: Optional[asyncpg.Record] = res[0] if res else None
    if not server:
        return "Invalid subscription or server not found", 404
    ip_address = server.get("ip_address", None)
    saved_ports = server.get("ports", "{}")
    saved_ports = json.loads(saved_ports)

    # Fetch subscription
    res = await db.db_select_subscription_by_id(subscription_id)
    subscription: Optional[asyncpg.Record] = res[0] if res else None

    if not subscription:
        return "Subscription  found", 404

    # CPU/Memory usage — static placeholders (replace with actual call later)
    cpu_usage_percent = 43  # Example static value
    memory_usage_percent = 68  # Example static value

    # Server running status
    server_status = server["status"]

    return await render_template(
        "monitoring.html",
        ports=saved_ports,
        ip_address=ip_address,
        subscription_id=subscription_id,
        cpu_usage_percent=cpu_usage_percent,
        memory_usage_percent=memory_usage_percent,
        server_status=server_status,
        subscription=subscription,
    )


@userblueprint.route("/server-status", methods=["GET", "POST"])
@login_required
async def server_status():
    args = request.args
    subscription_id = args.get("subscription_id", "")
    server, err = await db.db_select_server_by_subscription_id(subscription_id)
    if not server:
        logger.warning(err)
        return {"status": "Error getting server status"}

    data = {"status": server.get("status", "")}
    return data


@userblueprint.route("/configure", methods=["GET", "POST"])
@login_required
async def configure():
    """
    Server configuration route.

    Allows users to configure their server settings.

    Returns:
        HTML template with configuration options
    """
    args = request.args
    subscription_id = args.get("subscription_id")
    try:
        if not subscription_id:
            logger.warning("Missing subscription_id in configure route")
            return await render_template(
                "configure.html", config=None, error="Missing subscription ID"
            )

        record, err = await db.db_select_server_by_subscription_id(subscription_id)
        if not record:
            logger.warning(f"No servers found for subscription: {subscription_id}")
            return await render_template(
                "configure.html", config=None, error="No servers found"
            )

        provisioner = MainProvisioner()
        db_cfg: Dict[str, Any] = json.loads(record.get("config", "{}"))
        config: Optional[
            Dict[str, Any]
        ] = await provisioner.generate_config_view_schema(db_cfg, subscription_id)

        return await render_template(
            "configure.html",
            config=config,
            subscription_id=subscription_id,
        )
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON config for subscription: {subscription_id}")
        return await render_template(
            "configure.html", config=None, error="Invalid server configuration"
        )
    except Exception as e:
        logger.exception(f"Error loading server configuration: {str(e)}")
        return await render_template(
            "configure.html", config=None, error="Failed to load configuration"
        )


@userblueprint.route("/mods_n_backups", methods=["GET"])
@login_required
async def mods_n_backups():
    subscription_id = request.args.get("subscription_id", "")
    server, err = await db.db_select_server_by_subscription_id(subscription_id)
    if not server:
        return await render_template(
            "mods_n_backups.html", sftp_username=None, sftp_password=None
        )

    sftp_username = server.get("sftp_username", "")
    sftp_password = server.get("sftp_password", "")
    return await render_template(
        "mods_n_backups.html", sftp_username=sftp_username, sftp_password=sftp_password
    )


@userblueprint.route("/order_server")
@login_required
async def order_server():
    return await render_template("test.html")
