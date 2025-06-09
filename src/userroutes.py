"""
User authentication and management routes for Quart web application.

This module provides routes for user registration, login, dashboard access,
and server management functionality.
"""

import datetime
import json
import logging
from typing import Dict, Optional, Tuple, List, Any
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
            password=pwd_context.hash(fields["password"][0]),
            game_id=fields["game_id"][0],
            plan_id=fields["plan_id"][0],
        )

        # Insert user into database
        logger.info(data)
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


@userblueprint.route("/subscription-status/<string:subscription_id>", methods=["GET", "POST"])
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

@userblueprint.route("/server-status", methods=["GET", "POST"])
@login_required
async def server_status():
    args = request.args
    subscription_id = args.get("subscription_id","")
    server, err = await db.db_select_server_by_subscription(subscription_id)
    if not server:
        return "Error getting server status"

    data = {"status":server.get("status","")}
    return data



@userblueprint.route("/panel", methods=["GET", "POST"])
@login_required
async def panel():
    args = request.args
    subscription_id = args.get("subscription_id")
    return await render_template("panel.html", subscription_id=subscription_id)


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

        record, err = await db.db_select_server_by_subscription(subscription_id)
        if not record:
            logger.warning(f"No servers found for subscription: {subscription_id}")
            return await render_template(
                "configure.html", config=None, error="No servers found"
            )

        provisioner = MainProvisioner()
        db_cfg: Dict[str, Any] = json.loads(record.get("config", "{}"))
        config = await provisioner.generate_config_view_schema(db_cfg, subscription_id)
        ip_address = record.get("ip_address", None)
        ports = record.get("ports", "")
        main_port = ports.split(",")[0]

        return await render_template(
            "configure.html",
            ip_address=ip_address,
            main_port=main_port,
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


@userblueprint.route("/save-config", methods=["POST"])
@login_required
async def save_config():
    provisioner = MainProvisioner()
    subscription_id = request.args.get("subscription_id", "")
    error_html = "<p>Error updating the configuration</p>"
    success_html = "<p>Success</p>"

    server, err = await db.db_select_server_by_subscription(
        subscription_id=subscription_id
    )

    def log_error(err):
        logger.error(
            f"Error when updating configuration server:{server} of subscription_id:{subscription_id} err:{err} "
        )

    if not server or not subscription_id:
        log_error(err)
        return error_html

    subscription, err = await db.db_select_subscription_by_id(sub_id=subscription_id)
    if not subscription:
        log_error(err)
        return error_html

    plan, err = await db.db_select_plan_by_id(str(subscription.get("plan_id", "")))
    if not plan:
        log_error(err)
        return error_html

    game, err = await db.db_select_game_by_id(str(plan.get("game_id", "")))
    if not game or not game.get("game_name", None):
        log_error(err)
        return error_html

    ip = server.get("ip_address", "")
    game_name = game.get("game_name", "")

    # take care of nestings 1level and ints
    raw_config_values = await request.form
    config_values = {}
    for key, value in raw_config_values.items():
        v = value
        try:
            v = int(v)
        except ValueError:
            pass
        if "[" in key and "]" in key:
            top_level_name = key.split("[")[0]
            second_level_name = (key.split("[")[1]).split("]")[0]
            if not config_values.get(top_level_name, None):
                config_values[top_level_name] = {}
            config_values[top_level_name][second_level_name] = v
            continue
        config_values[key] = v

    result, _ = await db.db_update_server_config(
        config=json.dumps(config_values), server_id=str(server.get("id", ""))
    )
    await provisioner.job_update_config(
        game_server_ip=ip,
        game_name=game_name,
        subscription_id=subscription_id,
        config_values=config_values,
    )

    return success_html


@userblueprint.route("/mods_n_backups", methods=["GET"])
@login_required
async def mods_n_backups():
    subscription_id = request.args.get("subscription_id", "")
    server, err = await db.db_select_server_by_subscription(subscription_id)
    if not server:
        return await render_template(
            "mods_n_backups.html", sftp_username=None, sftp_password=None
        )

    sftp_username = server.get("sftp_username", "")
    sftp_password = server.get("sftp_password", "")
    return await render_template(
        "mods_n_backups.html", sftp_username=sftp_username, sftp_password=sftp_password
    )


@userblueprint.route("/monitoring", methods=["GET"])
@login_required
async def monitoring():
    subscription_id = request.args.get("subscription_id", "")
    if not subscription_id:
        return "Missing subscription_id", 400

    # Fetch server linked to this subscription
    res = await db.db_select_server_by_subscription(subscription_id)
    server: Optional[asyncpg.Record] = res[0] if res else None

    # Fetch subscription
    res = await db.db_select_subscription_by_id(subscription_id)
    subscription: Optional[asyncpg.Record] = res[0] if res else None

    if not server or not subscription:
        return "Invalid subscription or server not found", 404

    # CPU/Memory usage — static placeholders (replace with actual call later)
    cpu_usage_percent = 43  # Example static value
    memory_usage_percent = 68  # Example static value

    # Ports → comma-separated string
    server_ports = []
    if server.get("ports"):
        server_ports = [
            port.strip() for port in server["ports"].split(",") if port.strip()
        ]

    # Server running status
    server_status = server["status"]

    return await render_template(
        "monitoring.html",
        subscription_id=subscription_id,
        cpu_usage_percent=cpu_usage_percent,
        memory_usage_percent=memory_usage_percent,
        server_ip=server["ip_address"],
        server_ports=server_ports,  # List of ports
        server_status=server_status,
        subscription=subscription,
    )


@userblueprint.route("/restart_server", methods=["POST"])
@login_required
async def restart_server():
    redis_Client = db.get_redis_client()
    subscription_id = request.args.get("subscription_id", "")
    # Enqueue restart action to Redis queue here
    server, err = await db.db_select_server_by_subscription(subscription_id)
    if not server:
        return "Error when restarting server"
    subsciption, err = await db.db_select_subscription_by_id(subscription_id)
    if not subsciption:
        return "Error when restarting server"
    plan, err = await db.db_select_plan_by_id(str(subsciption.get("plan_id", "")))
    if not plan:
        return "Error when restarting server"
    game, err = await db.db_select_game_by_id(str(plan.get("game_id", "")))
    if not game:
        return "Error when restarting server"
    game_name = game.get("game_name", "")
    await db.db_update_server_status(
        status="restarting",
        docker_container_id=server.get("docker_container_id", ""),
        subscription_id=subscription_id,
        ports=server.get("ports", ""),
    )
    ip = server.get("ip_address", "")
    queueName = f"badger:pending:{ip}"
    payload = f"python3 setup_server.py -u {subscription_id} -g  {game_name} restart"
    await redis_Client.lpush(queueName, payload)
    return "Restarting"

@userblueprint.route("/backup_server", methods=["POST"])
@login_required
async def backup_server():
    redis_Client = db.get_redis_client()
    subscription_id = request.args.get("subscription_id", "")
    # Enqueue restart action to Redis queue here
    server, err = await db.db_select_server_by_subscription(subscription_id)
    if not server:
        return "Error when backing server"
    subsciption, err = await db.db_select_subscription_by_id(subscription_id)
    if not subsciption:
        return "Error when backing server"
    plan, err = await db.db_select_plan_by_id(str(subsciption.get("plan_id", "")))
    if not plan:
        return "Error when backing server"
    game, err = await db.db_select_game_by_id(str(plan.get("game_id", "")))
    if not game:
        return "Error when backing server"
    game_name = game.get("game_name", "")
    await db.db_update_server_status(
        status="backing up",
        docker_container_id=server.get("docker_container_id", ""),
        subscription_id=subscription_id,
        ports=server.get("ports", ""),
    )
    ip = server.get("ip_address", "")
    queueName = f"badger:pending:{ip}"
    payload = f"python3 setup_server.py -u {subscription_id} -g  {game_name} backup"
    await redis_Client.lpush(queueName, payload)
    return "backing up"

@userblueprint.route("/stop_server", methods=["POST"])
@login_required
async def stop_server():
    redis_Client = db.get_redis_client()
    subscription_id = request.args.get("subscription_id", "")
    # Enqueue restart action to Redis queue here
    server, err = await db.db_select_server_by_subscription(subscription_id)
    if not server:
        return "Error when stopping server"
    subsciption, err = await db.db_select_subscription_by_id(subscription_id)
    if not subsciption:
        return "Error when stopping server"
    plan, err = await db.db_select_plan_by_id(str(subsciption.get("plan_id", "")))
    if not plan:
        return "Error when stopping server"
    game, err = await db.db_select_game_by_id(str(plan.get("game_id", "")))
    if not game:
        return "Error when stopping server"
    game_name = game.get("game_name", "")
    await db.db_update_server_status(
        status="stopping",
        docker_container_id=server.get("docker_container_id", ""),
        subscription_id=subscription_id,
        ports=server.get("ports", ""),
    )
    ip = server.get("ip_address", "")
    queueName = f"badger:pending:{ip}"
    payload = f"python3 setup_server.py -u {subscription_id} -g  {game_name} stop"
    await redis_Client.lpush(queueName, payload)
    return "stopping"
