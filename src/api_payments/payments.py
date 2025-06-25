import datetime
from enum import verify
import logging
from typing import Dict
from quart import Blueprint, abort
from quart import request
from db import db
import hmac
import hashlib

paymentBluePrint = Blueprint("paymentBluePrint", __name__)


lemon_squeezy_secret = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiI5NGQ1OWNlZi1kYmI4LTRlYTUtYjE3OC1kMjU0MGZjZDY5MTkiLCJqdGkiOiIyMWY1ZGZkMWVhMjUyZWYzOWJhM2RmNmJkODcyNmFmMzkyYjYzYjI3MWVjMjhlMTlkOWE5NzI3MTY0YjQ1NDYwZjAxYzNiNmUyMjQwYTkwZSIsImlhdCI6MTc1MDc1NzM4OC4yMTM2MDgsIm5iZiI6MTc1MDc1NzM4OC4yMTM2MTEsImV4cCI6MjA2NjI5MDE4OC4xNzY2NDgsInN1YiI6IjUwOTQ2MDQiLCJzY29wZXMiOltdfQ.hscdyudwsjUGotjSOk3Qw9saWOJ-lnuibFOiHG9B1ruMgptRu_qSglffoGn7ag6bduxW76bfIDnoaPhZvE7tECNkP-w9zf6zdIq-XwKQo8q2AKRTnQLlDPFZRLmUynF92v8NgDsiABf8r4LZsiCHvBzcKRzY8d7BoSrUbEOM784ianVcqpTjwJfEGx73x6jRsy2y8D7pKYhgI0rT_dyUM1xbWnGDkAwWMo-3hgGO2XE5b2nxLTqRxHBy9-kqZvIcQ3PD_Gc6NIHEWpzuiIxcQSeAS-vmAyU269pYmsFqDhP6xDZEJoDGB9JbgKtmKa4C83566NNIDAWoMQKXaGyOg29_fuGyGuBWgk_ypxE7oyxwgIGJ_YAHo2eeeqLKgTg5PILN2IYP8y9ByN8Z0U1-9HUfX5NZQxWLIHL8IF5qkmihQWEasZvoTStBwQefStMYmocr530NBiYP0jqh5He_JEwP58OdrGRp4InEH2ar97Cb7J-VpHL9utHDg_P6Bfen"


def verify_lemon_squeezy_webhook(signing_secret, request_body, signature_header):
    # Compute HMAC SHA256
    computed_signature = hmac.new(
        key=signing_secret.encode("utf-8"), msg=request_body, digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed_signature, signature_header)


@paymentBluePrint.route("/webhook", methods=["POST"])
async def webhook():
    logger = logging.getLogger("backendlogger")
    body = await request.body
    X_Signature = request.headers.get("X-Signature", None)
    if not X_Signature:
        return abort(400)
    if not verify_lemon_squeezy_webhook("batcave", body, X_Signature):
        return abort(403)
    rq = await request.json

    event_name = rq["meta"]["event_name"]
    logger.info(event_name)

    if HANDLERS.get(event_name, None):
        await HANDLERS[event_name](rq)
    else:
        pass

    logger = logging.getLogger("backendlogger")
    logger.info("data")
    return {"successful": True}, 200


async def subscription_created(rq: Dict):
    logger = logging.getLogger("backendlogger")
    try:
        meta = rq["meta"]
        data = rq["data"]

        user_id = meta["custom_data"]["user_id"]
        plan_id = meta["custom_data"]["plan_id"]
        status = data["attributes"]["status"]
        paddle_subscription_id = data["attributes"]["first_subscription_item"][
            "subscription_id"
        ]
        paddle_customer_id = data["attributes"]["customer_id"]
        renews_at = data["attributes"]["renews_at"]
        renews_at_dt = datetime.datetime.fromisoformat(renews_at.replace("Z", "+00:00"))
        _, err = await db.db_insert_subscription_with_payment(
            user_id=user_id,
            plan_id=str(plan_id),
            status=status,
            paddle_subscription_id=str(paddle_subscription_id),
            paddle_customer_id=str(paddle_customer_id),
            expires_at=renews_at_dt,
            next_billing_date=renews_at_dt,
        )
        if err:
            logger.error(f"Error inserting subscription: {err}")
            return {"error": "Failed to create subscription"}, 500

        logger.info(f"Subscription created successfully for user_id: {user_id}")
        return {"message": "Subscription created successfully"}, 200

    except Exception as e:
        logger.exception(f"Error processing subscription_created webhook: {e}")
        return {"error": "Internal server error"}, 500


async def subscription_updated(rq: Dict):
    logger = logging.getLogger("backendlogger")
    try:
        data = rq["data"]
        meta = rq["meta"]
        custom_data = meta.get("custom_data", {})

        user_id = custom_data.get("user_id")
        plan_id = custom_data.get("plan_id")
        paddle_subscription_id = data["attributes"]["first_subscription_item"][
            "subscription_id"
        ]
        status = data["attributes"]["status"]
        renews_at = data["attributes"]["renews_at"]
        renews_at_dt = datetime.datetime.fromisoformat(renews_at.replace("Z", "+00:00"))
        s = await db.db_update_subscription(
            paddle_subscription_id=str(paddle_subscription_id),
            user_id=user_id,
            plan_id=plan_id,
            status=status,
            next_billing_date=renews_at_dt,
            expires_at=renews_at_dt,
        )

        logger.info(f"Subscription updated successfully for user_id: {user_id}")
        return {"message": "Subscription updated successfully"}, 200

    except Exception as e:
        logger.exception(f"Error processing subscription_updated webhook: {e}")
        return {"error": "Internal server error"}, 500


async def subscription_cancelled(rq: Dict):
    logger = logging.getLogger("backendlogger")
    try:
        data = rq["data"]
        paddle_subscription_id = data["attributes"]["first_subscription_item"][
            "subscription_id"
        ]

        await db.db_cancel_subscription(
            paddle_subscription_id=str(paddle_subscription_id)
        )

        logger.info(
            f"Subscription cancelled successfully for paddle_subscription_id: {paddle_subscription_id}"
        )
        return {"message": "Subscription cancelled successfully"}, 200

    except Exception as e:
        logger.exception(f"Error processing subscription_cancelled webhook: {e}")
        return {"error": "Internal server error"}, 500


async def subscription_expired(rq: Dict):
    logger = logging.getLogger("backendlogger")
    try:
        data = rq["data"]
        meta = rq["meta"]
        custom_data = meta.get("custom_data", {})
        paddle_subscription_id = data["attributes"]["first_subscription_item"][
            "subscription_id"
        ]
        user_id = custom_data.get("user_id")

        await db.db_mark_subscription_expired(
            paddle_subscription_id=str(paddle_subscription_id), user_id=user_id
        )

        logger.info(
            f"Subscription expired successfully for paddle_subscription_id: {paddle_subscription_id}"
        )
        return {"message": "Subscription expired successfully"}, 200

    except Exception as e:
        logger.exception(f"Error processing subscription_expired webhook: {e}")
        return {"error": "Internal server error"}, 500


async def subscription_paused(rq: Dict):
    logger = logging.getLogger("backendlogger")
    try:
        data = rq["data"]
        meta = rq["meta"]
        custom_data = meta.get("custom_data", {})
        paddle_subscription_id = data["attributes"]["first_subscription_item"][
            "subscription_id"
        ]
        user_id = custom_data.get("user_id")

        await db.db_mark_subscription_paused(
            paddle_subscription_id=str(paddle_subscription_id), user_id=user_id
        )

        logger.info(
            f"Subscription paused successfully for paddle_subscription_id: {paddle_subscription_id}"
        )
        return {"message": "Subscription paused successfully"}, 200

    except Exception as e:
        logger.exception(f"Error processing subscription_paused webhook: {e}")
        return {"error": "Internal server error"}, 500


async def invoice_paid(rq: Dict):
    logger = logging.getLogger("backendlogger")
    try:
        data = rq["data"]
        meta = rq["meta"]
        custom_data = meta.get("custom_data", {})

        user_id = custom_data.get("user_id")
        paddle_subscription_id = data["attributes"]["first_subscription_item"][
            "subscription_id"
        ]

        # Fetch additional attributes from the Lemon Squeezy payload
        amount = data["attributes"]["amount_total"]  # Total amount paid
        description = data["attributes"].get(
            "description", "Invoice Payment"
        )  # Description of the payment
        payment_method = data["attributes"]["payment_method"]  # Payment method used
        payment_status = data["attributes"]["status"]  # Payment status
        created_at = data["attributes"]["created_at"]  # Payment creation timestamp
        paddle_transaction_id = data["attributes"]["id"]  # Unique transaction ID

        # Fetch the subscription from the database
        subscription, err = await db.db_select_subscription_by_paddle_subscription_id(
            paddle_subscription_id
        )
        if not subscription:
            logger.error(
                f"Subscription not found for paddle_subscription_id: {paddle_subscription_id} err:",
                err,
            )
            return {"error": "Subscription not found"}, 404

        # Insert the transaction into the database
        await db.db_insert_transaction(
            user_id=user_id,
            subscription_id=str(subscription.get("id", "")),
            amount=amount,
            description=description,
            payment_method=payment_method,
            payment_status=payment_status,
            created_at=created_at,
            paddle_transaction_id=paddle_transaction_id,
        )

        logger.info(
            f"Invoice paid successfully for user_id: {user_id}, subscription_id: {subscription.get('id')}"
        )
        return {"message": "Invoice processed successfully"}, 200

    except Exception as e:
        logger.exception(f"Error processing invoice_paid webhook: {e}")
        return {"error": "Internal server error"}, 500


HANDLERS = {
    "subscription_created": subscription_created,
    "subscription_cancelled": subscription_cancelled,
    "subscription_updated": subscription_updated,
    "subscription_expired": subscription_expired,
    "subscription_paused": subscription_paused,
}
