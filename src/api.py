"""
API endpoints for server status reporting and management.

This module provides API routes for game servers to report their status
and update subscription information in the database.
"""

import datetime
import logging
from typing import Callable, Dict, Any, Optional, Tuple, List

from quart import Blueprint, request, Response
from db import db

# Create module-level logger
logger = logging.getLogger("backendlogger")

# Blueprint definition
apiblueprint = Blueprint("api", __name__)


class RegisterHandler:
    registry: Dict[str, Callable] = {}

    def __init__(self):
        self.registry["start"] = self._start_handler
        self.registry["stop"] = self._stop_handler
        self.registry["restart"] = self._start_handler
        self.registry["status"] = self._status_handler
        self.registry["backup"] = self._backup_handler
        self.registry["updateConfig"] = self._update_config_handler

    async def handle_report(
        self, action: str, data: Dict
    ) -> Tuple[bool, Optional[str]]:
        if action not in self.registry.keys():
            return (
                False,
                f"Unknown action available actions are <{self.registry.keys()}>",
            )
        return await self.registry[action](data)

    @staticmethod
    def _check_fields(
        required_fields: List[str], data: Dict
    ) -> Tuple[bool, Optional[str]]:
        for field in required_fields:
            if field not in data:
                return False, field
        return True, None

    async def _start_handler(self, data: Dict) -> Tuple[bool, Optional[Dict]]:
        # Validate required fields

        required_fields = ["status", "container_id", "subscription_id"]
        pass_check, missing_field = self._check_fields(required_fields, data)
        if not pass_check:
            logger.warning(f"Missing required field in _start_handler: {missing_field}")
            return False, {
                "status": "error",
                "message": f"Missing required field: {missing_field}",
            }

        # Update server status in the database
        try:
            ports = ""
            if "ports" in data.keys():
                for p in data["ports"]:
                    ports += str(p) + ","
            server, err = await db.db_update_server_status(
                status=data["status"],
                docker_container_id=data["container_id"],
                subscription_id=data["subscription_id"],
                ports=ports,
            )
            if err:
                return False, {"status": "error", "message": err}

            if "metrics" in data.keys():
                pwd = data["metrics"].get("password")
                username = data["metrics"].get("username")
                _, err = await db.db_update_server_sftp(
                    sftp_username=username,
                    sftp_password=pwd,
                    server_id=str(server.get("id", "")),
                )
                if err:
                    return False, {"status": "error", "message": err}

            logger.info(
                f"Server status updated for subscription: {data['subscription_id']}"
            )
        except Exception as e:
            logger.exception(f"Failed to update server status: {str(e)}")
            return False, {
                "status": "error",
                "message": "Database error updating server",
            }

        # Update subscription billing dates
        try:
            now = datetime.datetime.now(datetime.UTC)
            next_billing_date = now + datetime.timedelta(days=30)
            await db.db_update_subscription_status(
                subscription_id=data["subscription_id"],
                status=data["status"],
                last_billing_date=now,
                next_billing_date=next_billing_date,
            )
            logger.info(
                f"Subscription updated for ID: {data['subscription_id']}, next billing: {next_billing_date}"
            )
        except Exception as e:
            logger.exception(f"Failed to update subscription: {str(e)}")
            return False, {
                "status": "error",
                "message": "Database error updating subscription",
            }

        return True, None

    async def _stop_handler(self, data: Dict) -> Tuple[bool, Optional[Dict]]:
        required_fields = ["subscription_id", "status"]
        pass_check, missing_field = self._check_fields(required_fields, data)
        if not pass_check:
            logger.warning(f"Missing required field in _stop_handler: {missing_field}")
            return False, {
                "status": "error",
                "message": f"Missing required field: {missing_field}",
            }

        server, err = await db.db_select_server_by_subscription(data["subscription_id"])
        if err or not server:
            logger.warning(
                f"Error when selecting server by subscription_id {data['subscription_id']} :{err}"
            )
            return False, {
                "status": "error",
                "message": f"Error when selecting server by subscription_id {data['subscription_id']}",
            }

        server, err = await db.db_update_server_status(
            status=data["status"],
            docker_container_id=server.get("docker_container_id", ""),
            subscription_id=data["subscription_id"],
        )
        if err or not server:
            logger.warning(
                f"Error when selecting updating server status in _stop_handler by subscription_id {data['subscription_id']} :{err}"
            )
            return False, {"status": "error", "message": "Error when stopping server"}
        logger.info(f"Server stoped for subscription: {data['subscription_id']}")
        return True, None

    async def _status_handler(self, data: Dict) -> Tuple[bool, Optional[Dict]]:
        required_fields = ["subscription_id", "status", "container_id", "metrics"]
        pass_check, missing_field = self._check_fields(required_fields, data)
        if not pass_check:
            logger.warning(
                f"Missing required field in _status_handler: {missing_field}"
            )
            return False, {
                "status": "error",
                "message": f"Missing required field: {missing_field}",
            }
        logger.info(
            f"Server status obtained for subscription: {data['subscription_id']}"
        )
        return True, None

    async def _backup_handler(self, data: Dict) -> Tuple[bool, Optional[Dict]]:
        required_fields = ["subscription_id", "status", "container_id", "metrics"]
        pass_check, missing_field = self._check_fields(required_fields, data)
        if not pass_check:
            logger.warning(
                f"Missing required field in _backup_handler: {missing_field}"
            )
            return False, {
                "status": "error",
                "message": f"Missing required field: {missing_field}",
            }
        logger.info(f"Server backup done for subscription: {data['subscription_id']}")
        return True, None

    async def _update_config_handler(self, data: Dict) -> Tuple[bool, Optional[Dict]]:
        print("update called")
        required_fields = ["subscription_id", "status"]
        pass_check, missing_field = self._check_fields(required_fields, data)
        if not pass_check:
            logger.warning(
                f"Missing required field in _update_config_handler: {missing_field}"
            )
            return False, {
                "status": "error",
                "message": f"Missing required field: {missing_field}",
            }

        logger.info(
            f"Server config update done for subscription: {data['subscription_id']}"
        )
        return True, None


@apiblueprint.route("/api/server_report", methods=["POST"])
async def register_server() -> Response:
    """
    Process server status reports from game servers.

    This endpoint receives status updates from running game servers,
    updates server and subscription records in the database,
    and manages billing dates.

    Returns:
        JSON response with status information
    """
    try:
        # Get request data
        data: Dict[str, Any] = await request.get_json()

        # Validate request data
        if not data:
            logger.warning("Empty server report received")
            return Response(
                response={"status": "error", "message": "No data provided"}, status=400
            )

        # Log the received data
        logger.info(f"Server report received: {data}")

        # Check for error reports
        error: Optional[str] = data.get("error")
        if error:
            logger.error(f"Server error reported: {error}")
            return Response({"status": "received", "error_logged": True}, 200)
        action = data.get("action")
        if not action:
            logger.error("No action in report")
            return Response({"status": "received", "error_logged": True}, 200)

        rh = RegisterHandler()
        success, err = await rh.handle_report(action=action, data=data)
        if not success:
            return Response({"status": "received", "error_logged": True}, 200)

    except Exception as e:
        logger.exception(f"Unexpected error in server_report: {str(e)}")
        return Response({"status": "error", "message": "Internal server error"}, 500)

    return Response({"status": "success", "action": action})
