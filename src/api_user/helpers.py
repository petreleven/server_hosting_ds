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
        now = datetime.datetime.now(datetime.timezone.utc)

        if expires_at:
            timediff = expires_at - now
            is_expiring_soon = timediff.total_seconds() < (8 * 60 * 60)
        else:
            is_expiring_soon = False

        subscription = {
            "id": record.get("id"),
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
