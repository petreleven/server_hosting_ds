"""
API endpoints for server status reporting and management.

This module provides API routes for game servers to report their status
and update subscription information in the database.
"""

import datetime
import logging
from typing import Dict, Any, Optional

from quart import Blueprint, request, Response
from db import db

# Create module-level logger
logger = logging.getLogger("backendlogger")

# Blueprint definition
apiblueprint = Blueprint("api", __name__)


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

        # Validate required fields
        required_fields = ["status", "container_id", "subscription_id"]
        for field in required_fields:
            if field not in data:
                logger.warning(f"Missing required field in server report: {field}")
                return Response(
                    {"status": "error", "message": f"Missing required field: {field}"},
                    400,
                )

        # Update server status in the database
        try:
            await db.db_update_server_status(
                status=data["status"],
                docker_container_id=data["container_id"],
                subscription_id=data["subscription_id"],
            )
            logger.info(
                f"Server status updated for subscription: {data['subscription_id']}"
            )
        except Exception as e:
            logger.exception(f"Failed to update server status: {str(e)}")
            return Response(
                {"status": "error", "message": "Database error updating server"}, 500
            )

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
            return Response(
                {"status": "error", "message": "Database error updating subscription"},
                500,
            )

        # Return success response
        return Response(
            {
                "status": "success",
                "message": "Server and subscription updated",
                "next_billing_date": next_billing_date.isoformat(),
            },
            200,
        )

    except Exception as e:
        logger.exception(f"Unexpected error in server_report: {str(e)}")
        return Response({"status": "error", "message": "Internal server error"}, 500)
