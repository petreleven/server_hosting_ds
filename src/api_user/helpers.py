import logging
import asyncpg
import datetime
from typing import Dict, Any


async def extract_single_sub_record(record: asyncpg.Record) -> Dict[str, Any]:
    """
    Extract subscription data from database record.

    Args:
        record: Database record containing subscription data

    Returns:
        Dictionary with formatted subscription data
    """
    logger = logging.getLogger("backendlogger")
    if not record:
        logger.warning("Attempted to extract subscription from empty record")
        return {}

    try:
        expires_at = record.get("expires_at")

        subscription = {
            "id": record.get("id"),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "expires_at": expires_at,
            "internal_status": record.get("internal_status"),
            "last_billing_date": record.get("last_billing_date"),
            "next_billing_date": record.get("next_billing_date"),
        }

        return subscription
    except Exception as e:
        logger.exception(f"Error extracting subscription data: {str(e)}")
        return {}
