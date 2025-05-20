import datetime
import logging

from quart import Blueprint, request

from db import db

apiblueprint = Blueprint("api", __name__)


@apiblueprint.route("/api/server_report", methods=["POST"])
async def register_server():
    backendlogger = logging.getLogger("backendlogger")
    data: dict = await request.json
    if not data:
        return {}
    backendlogger.info(data)
    err: str | None = data.get("error")

    if err:
        backendlogger.warning(data["error"])
        return {}
    await db.db_update_server_status(
        status=data["status"],
        docker_container_id=data["container_id"],
        subscription_id=int(data["subscription_id"]),
    )
    now = datetime.datetime.now(datetime.UTC)
    next_billing_date = now + datetime.timedelta(days=30)
    await db.db_update_subscription_status(
        subscription_id=int(data["subscription_id"]),
        status=data["status"],
        last_billing_date=now,
        next_billing_date=next_billing_date,
    )
    return {}
