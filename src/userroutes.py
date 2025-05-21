import datetime
import json
import logging
from typing import Dict
from urllib.parse import parse_qs

import asyncpg
from passlib.context import CryptContext
from quart import Blueprint, current_app, redirect, render_template, request, url_for
from quart_auth import AuthUser, current_user, login_required, login_user, logout_user

import custom_dataclass as cdata
from db import db
from game_jobs.mainProvisioner import MainProvisioner

userblueprint = Blueprint("userroute", __name__)
pwd_context = CryptContext(schemes=["bcrypt"])
SECRET = "ygQpJHb0MNDCK0Loa1OeN.wiJH0cuiGOdZnAwW4fQlw5iqo6luZrS"


@userblueprint.route("/register", methods=["GET", "POST"])
async def register():
    provisioner = MainProvisioner()
    app = current_app
    req_data: bytearray = await request.body
    fields: dict[str, list] = parse_qs(req_data.decode("utf-8"))
    data = cdata.RegisterUserData(
        email=fields["email"][0],
        password=pwd_context.hash(fields["password"][0]),
        game_id=fields["game_id"][0],
        plan_id=fields["plan_id"][0],
    )
    u = await db.db_insert_user(data)
    if not u:
        return redirect(url_for("/"))
    user_id = u.get("id")
    if not user_id:
        return redirect(url_for("/"))

    login_user(AuthUser(auth_id=user_id))
    if not u:
        backendlogger = logging.getLogger("backendlogger")
        backendlogger.warning(f"Unable to Create Account for {data.email}")
    app.add_background_task(provisioner.job_order_new_server, data)
    return redirect("dashboard")


@userblueprint.route("/dashboard", methods=["GET", "POST"])
@login_required
async def dashboard():
    # login_user(AuthUser("42"))
    if not request.headers.get("Hx-Request"):
        return await render_template("dashboard_full.html")
    return await render_template("dashboard_partial.html")


@userblueprint.route("/", methods=["GET", "POST"])
async def home():
    return await render_template("home.html")


@userblueprint.route("/signup", methods=["GET", "POST"])
async def signup():
    return await render_template("signup.html")


async def verify_user(fields: dict[str, list]) -> tuple[bool, dict[str, str], str]:
    email_list = fields.get("email")
    password_list = fields.get("password")

    res = False
    errors: dict[str, str] = {}

    if not email_list or not email_list[0]:
        errors["email_error"] = "Please provide email"
        return res, errors, "-1"
    if not password_list or not password_list[0]:
        errors["password_error"] = "Please provide password"
        return res, errors, "-1"

    email = email_list[0]
    password = password_list[0]
    record: asyncpg.Record | None = await db.db_select_user_by_email(email=email)
    if not record:
        errors["email_error"] = "No user by that email exists"
        return res, errors, "-1"

    res = pwd_context.verify(password, record.get("password", ""))
    if not res:
        errors["password_error"] = "Please check password"
    return res, errors, record.get("id")


@userblueprint.route("/login", methods=["GET", "POST"])
async def login():
    errors = {}

    if request.method == "POST":
        body = (await request.body).decode("utf-8")
        fields: dict[str, list] = parse_qs(body)
        (res, errors, id) = await verify_user(fields)
        if res:
            login_user(AuthUser(id))
            return redirect("/dashboard")

    return await render_template("login.html", errors=errors)


@userblueprint.route("/logout", methods=["GET"])
async def logout():
    logout_user()
    return redirect("/")


async def extract_single_sub_record(record: asyncpg.Record) -> Dict:
    expires_at = record.get("expires_at")
    now = datetime.datetime.now(datetime.UTC)
    timediff = now - expires_at
    is_expiring_soon = timediff.total_seconds() < (2 * 24 * 60 * 60)

    subscription = {
        "id": record.get("id"),
        "tier": "free",
        "is_expiring_soon": is_expiring_soon,
        "status": record.get("status"),
        "created_at": record.get("created_at"),
        "expires_at": record.get("expires_at"),
        "last_billing_date": record.get("last_billing_date"),
        "next_billing_date": record.get("next_billing_date"),
    }

    return subscription


@userblueprint.route("/dashboardservers", methods=["GET", "POST"])
@login_required
async def dashboardservers():
    user_id = current_user.auth_id
    if not user_id:
        return []

    allsubs = await db.db_select_all_subscriptions(user_id=user_id)

    subscriptions = []
    for record in allsubs:
        sub = await extract_single_sub_record(record)
        subscriptions.append(sub)

    return await render_template("servers.html", subscriptions=subscriptions)


@userblueprint.route("/server-status/<str:subscription_id>", methods=["GET", "POST"])
@login_required
async def server_status(subscription_id):
    record = await db.db_select_subscription_by_id(subscription_id)
    if not record:
        return {}
    sub = await extract_single_sub_record(record)
    return await render_template("server_single.html", sub=sub)


@userblueprint.route("/configure", methods=["GET", "POST"])
@login_required
async def configure():
    args = request.args
    subscription_id = args.get("subscription_id", None)

    if not subscription_id:
        return []
    record = await db.db_select_servers_by_subscription(subscription_id)
    if not record:
        return []
    config = json.loads(record.get("config"))
    # Ensure 'config' is passed to the template
    return await render_template("configure.html", config=config)
