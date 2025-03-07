"""
User authentication and management routes for Quart web application.

This module provides routes for user registration, login, dashboard access,
and server management functionality.
"""

import asyncio
import datetime
import json
import logging
from typing import Dict, Tuple, List, Any
from urllib.parse import parse_qs

import asyncpg
from passlib.context import CryptContext
from quart import Blueprint, current_app, redirect, render_template, request, url_for
from quart_auth import AuthUser, current_user, login_required, login_user, logout_user

import custom_dataclass as cdata
from db import db
from game_jobs.mainProvisioner import MainProvisioner

# Create logger
logger = logging.getLogger(__name__)

# Blueprint definition
userblueprint = Blueprint("userroute", __name__)

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"])

# TODO: Remove hardcoded secret and use environment variable
SECRET = "ygQpJHb0MNDCK0Loa1OeN.wiJH0cuiGOdZnAwW4fQlw5iqo6luZrS"


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
        "password_error": [],
        "game_id_errors": [],
        "plan_id_errors": [],
        "general_errors": [],
    }
    app = current_app
    provisioner = MainProvisioner()

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
            password=pwd_context.hash(fields["password"][0]),
            game_id=fields["game_id"][0],
            plan_id=fields["plan_id"][0],
        )

        # Insert user into database
        user_record, err = await db.db_insert_user(data)

        if not user_record:
            errors["email_errors"].append(err)
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
        app.add_background_task(provisioner.job_order_new_server, data)
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


@userblueprint.route("/", methods=["GET", "POST"])
async def home():
    """
    Home page route.

    Returns:
        Home page template
    """
    return await render_template("home.html", errors={})


@userblueprint.route("/signup", methods=["GET", "POST"])
async def signup():
    """
    Signup page route.

    Returns:
        Signup page template
    """
    return await render_template("signup.html")


async def verify_user(
    fields: Dict[str, List[str]],
) -> Tuple[bool, Dict[str, List[str]], str]:
    """
    Verify user credentials.

    Args:
        fields: Form fields containing email and password

    Returns:
        Tuple containing:
        - Boolean indicating if verification was successful
        - Dictionary of error messages
        - User ID if successful, "-1" otherwise
    """
    errors: Dict[str, List[str]] = {
        "email_errors": [],
        "password_errors": [],
        "general_errors": [],
    }

    # Validate fields
    if not fields.get("email") or not fields["email"][0]:
        errors["email_errors"].append("Please provide email")
        return False, errors, "-1"

    if not fields.get("password") or not fields["password"][0]:
        errors["password_errors"].append("Please provide password")
        return False, errors, "-1"

    email = fields["email"][0]
    password = fields["password"][0]

    # Look up user by email
    record, err = await db.db_select_user_by_email(email=email)
    if not record:
        errors["email_errors"].append("No user by that email exists")
        logger.warning(f"Login attempt for non-existent user: {email}")
        return False, errors, "-1"

    # Verify password
    hashed_password = record.get("password", "")
    print(hashed_password)
    is_verified = (
        pwd_context.verify(password, hashed_password) if hashed_password else False
    )

    if not is_verified:
        errors["password_errors"].append("Please check password")
        logger.warning(f"Failed login attempt for user: {email}")

    return is_verified, errors, record.get("id", "-1")


@userblueprint.route("/login", methods=["GET", "POST"])
async def login():
    """
    User login route.

    Handles user login by verifying credentials and creating a session.

    Returns:
        Login page template or redirect to dashboard"""

    errors: Dict[str, List[str]] = {
        "email_errors": [],
        "password_errors": [],
        "general_errors": [],
    }

    if request.method == "POST":
        try:
            body = (await request.body).decode("utf-8")
            fields: Dict[str, List[str]] = parse_qs(body)
            (is_verified, errors, user_id) = await verify_user(fields)

            if is_verified:
                login_user(AuthUser(str(user_id)))
                logger.info(f"User logged in: {fields.get('email', ['<unknown>'])[0]}")
                return redirect(url_for("userroute.dashboard"))

        except Exception as e:
            errors["general_errors"].append("An error occurred during login")
            logger.exception(f"Exception during login: {str(e)}")
    print(errors)
    return await render_template("login.html", errors=errors)


@userblueprint.route("/logout", methods=["GET"])
async def logout():
    """
    User logout route.

    Logs out the current user and redirects to home page.

    Returns:
        Redirect to home page
    """
    logout_user()
    return redirect(url_for("userroute.home"))


async def extract_single_sub_record(record: asyncpg.Record) -> Dict[str, Any]:
    """
    Extract subscription data from database record.

    Args:
        record: Database record containing subscription data

    Returns:
        Dictionary with formatted subscription data
    """
    if not record:
        logger.warning("Attempted to extract subscription from empty record")
        return {}

    try:
        expires_at = record.get("expires_at")
        now = datetime.datetime.now(datetime.UTC)

        if expires_at:
            # Check if subscription is expiring soon (within 48 hours)
            timediff = expires_at - now  # Note: Fixed order of subtraction
            is_expiring_soon = timediff.total_seconds() < (2 * 24 * 60 * 60)
        else:
            is_expiring_soon = False

        subscription = {
            "id": record.get("id"),
            "tier": record.get("tier", "free"),
            "is_expiring_soon": is_expiring_soon,
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "expires_at": expires_at,
            "last_billing_date": record.get("last_billing_date"),
            "next_billing_date": record.get("next_billing_date"),
        }

        return subscription
    except Exception as e:
        logger.exception(f"Error extracting subscription data: {str(e)}")
        return {}


@userblueprint.route("/dashboardservers", methods=["GET", "POST"])
@login_required
async def dashboardservers():
    """
    Dashboard servers route.

    Displays the user's servers and their status.

    Returns:
        HTML template with server data
    """
    user_id = current_user.auth_id
    if not user_id:
        logger.warning("Missing user_id in dashboardservers route")
        return await render_template("servers.html", subscriptions=[])

    try:
        all_subs, err = await db.db_select_all_subscriptions(user_id=user_id)

        subscriptions = []
        for record in all_subs:
            sub = await extract_single_sub_record(record)
            if sub:  # Only append valid subscriptions
                subscriptions.append(sub)

        return await render_template("servers.html", subscriptions=subscriptions)
    except Exception as e:
        logger.exception(f"Error retrieving server data: {str(e)}")
        return await render_template(
            "servers.html", subscriptions=[], error="Failed to load servers"
        )


@userblueprint.route("/server-status/<string:subscription_id>", methods=["GET", "POST"])
@login_required
async def server_status(subscription_id: str):
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
                "server_single.html", current_sub=None, error="Invalid subscription ID"
            )

        record, err = await db.db_select_subscription_by_id(subscription_id)
        if not record:
            logger.warning(f"Subscription not found: {subscription_id}")
            return await render_template(
                "server_single.html", current_sub=None, error="Subscription not found"
            )

        current_sub = await extract_single_sub_record(record)
        return await render_template("server_single.html", current_sub=current_sub)
    except Exception as e:
        logger.exception(f"Error retrieving server status: {str(e)}")
        return await render_template(
            "server_single.html", current_sub=None, error="Failed to load server status"
        )

@userblueprint.route("/panel", methods=["GET", "POST"])
@login_required
async def panel():
    args = request.args
    subscription_id = args.get("subscription_id")
    return await render_template("panel.html",subscription_id=subscription_id)


@userblueprint.route("/configure", methods=["GET", "POST"])
@login_required
async def configure():
    """
    Server configuration route.

    Allows users to configure their server settings.

    Returns:
        HTML template with configuration options
    """
    print("yohh")
    try:
        args = request.args
        subscription_id = args.get("subscription_id")

        if not subscription_id:
            logger.warning("Missing subscription_id in configure route")
            return await render_template(
                "configure.html", config=None, error="Missing subscription ID"
            )

        record, err = await db.db_select_servers_by_subscription(subscription_id)
        if not record:
            logger.warning(f"No servers found for subscription: {subscription_id}")
            return await render_template(
                "configure.html", config=None, error="No servers found"
            )

        provisioner = MainProvisioner()
        db_cfg: Dict[str, Any] = json.loads(record.get("config", "{}"))
        config = await provisioner.generate_config_view_schema(db_cfg, subscription_id)

        return await render_template("configure.html", config=config)
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
