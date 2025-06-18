from quart import Quart, request, abort
import pprint
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from paddle_billing.Notifications import Verifier, Secret
from paddle_billing.Notifications.Requests import Request
from paddle_billing.Notifications.Requests.Headers import Headers

class QuartRequestAdapter:
    """Adapter to make Quart request compatible with Paddle Request protocol"""

    def __init__(self, quart_request, raw_body: bytes):
        self.body: Optional[bytes] = raw_body
        self.content: Optional[bytes] = raw_body
        self.data: Optional[bytes] = raw_body
        self.headers: Headers = quart_request.headers

# Mock database functions - replace with your actual DB logic
async def get_user_by_paddle_customer_id(paddle_customer_id: str):
    """Get user by Paddle customer ID"""
    # You'll need to store paddle_customer_id in users table or create mapping
    pass

async def get_plan_by_paddle_price_id(paddle_price_id: str):
    """Map Paddle price_id to your internal plan_id"""
    # You'll need a mapping table or store paddle_price_id in plans table
    pass

async def user_has_used_free_trial(user_id: str, plan_id: str) -> bool:
    """Check if user has already used free trial for this plan"""
    # Check if user has exhausted_free=True OR has any previous subscriptions for this plan
    pass

async def create_paid_subscription(data: Dict[str, Any]):
    """Create new PAID subscription in database"""
    subscription_data = {
        'user_id': data.get('user_id'),
        'plan_id': data.get('plan_id'),
        'status': 'active',  # Paid subscriptions start active
        'expires_at': data.get('next_billed_at'),
        'next_billing_date': data.get('next_billed_at'),
        'last_billing_date': datetime.now(),
        'paddle_subscription_id': data.get('paddle_subscription_id'),
        'is_trial': False  # This is a paid subscription
    }
    print(f"Creating PAID subscription: {subscription_data}")

    # Provision server immediately for paid subscription
    await provision_server(data.get('paddle_subscription_id'))

async def update_subscription_status(paddle_subscription_id: str, updates: Dict[str, Any]):
    """Update existing subscription by Paddle subscription ID"""
    print(f"Updating subscription {paddle_subscription_id}: {updates}")

async def create_transaction_record(data: Dict[str, Any]):
    """Create transaction record for payments"""
    transaction_data = {
        'user_id': data.get('user_id'),
        'subscription_id': data.get('subscription_id'),
        'amount': data.get('amount'),
        'description': data.get('description', ''),
        'payment_method': data.get('payment_method'),
        'payment_status': data.get('status', 'completed'),
        'paddle_transaction_id': data.get('paddle_transaction_id')
    }
    print(f"Creating transaction: {transaction_data}")

async def provision_server(paddle_subscription_id: str):
    """Provision server for paid subscription"""
    print(f"Provisioning server for PAID subscription: {paddle_subscription_id}")

async def suspend_server(paddle_subscription_id: str):
    """Suspend server for canceled/failed subscription"""
    print(f"Suspending server for subscription: {paddle_subscription_id}")

async def resume_server(paddle_subscription_id: str):
    """Resume server for resumed subscription"""
    print(f"Resuming server for subscription: {paddle_subscription_id}")

async def mark_user_trial_exhausted(user_id: str):
    """Mark user as having exhausted their free trial"""
    # UPDATE users SET exhausted_free = TRUE WHERE id = user_id
    print(f"Marking user {user_id} trial as exhausted")

# Event handlers for PAID subscriptions only
async def handle_subscription_created(data: Dict[str, Any]):
    """Handle new PAID subscription creation"""
    print("=== PAID SUBSCRIPTION CREATED ===")

    subscription = data.get('data', {})
    paddle_customer_id = subscription.get('customer_id')
    paddle_subscription_id = subscription.get('id')

    # Get user from paddle customer ID
    user = await get_user_by_paddle_customer_id(paddle_customer_id)
    if not user:
        print(f"User not found for Paddle customer: {paddle_customer_id}")
        return

    # Get plan from paddle price ID
    paddle_price_id = subscription.get('items', [{}])[0].get('price').get("id")
    plan = await get_plan_by_paddle_price_id(paddle_price_id)
    if not plan:
        print(f"Plan not found for Paddle price: {paddle_price_id}")
        return

    # Create PAID subscription (not trial)
    await create_paid_subscription({
        'user_id': user['id'],
        'plan_id': plan['id'],
        'paddle_subscription_id': paddle_subscription_id,
        'paddle_customer_id': paddle_customer_id,
        'status': subscription.get('status'),
        'next_billed_at': subscription.get('next_billed_at')
    })

    # Mark user as having exhausted free trial (they're now paying)
    await mark_user_trial_exhausted(user['id'])

async def handle_subscription_updated(data: Dict[str, Any]):
    """Handle subscription updates (plan changes, etc.)"""
    print("=== SUBSCRIPTION UPDATED ===")

    subscription = data.get('data', {})
    paddle_subscription_id = subscription.get('id')

    updates = {
        'status': subscription.get('status'),
        'expires_at': subscription.get('next_billed_at'),
        'next_billing_date': subscription.get('next_billed_at')
    }

    await update_subscription_status(paddle_subscription_id, updates)

async def handle_subscription_canceled(data: Dict[str, Any]):
    """Handle subscription cancellation"""
    print("=== SUBSCRIPTION CANCELED ===")

    subscription = data.get('data', {})
    paddle_subscription_id = subscription.get('id')

    # Update subscription status
    await update_subscription_status(paddle_subscription_id, {
        'status': 'canceled',
        'expires_at': subscription.get('canceled_at')
    })

    # Suspend server immediately or at end of billing period
    await suspend_server(paddle_subscription_id)

async def handle_subscription_paused(data: Dict[str, Any]):
    """Handle subscription pause (dunning)"""
    print("=== SUBSCRIPTION PAUSED (Payment Issues) ===")

    subscription = data.get('data', {})
    paddle_subscription_id = subscription.get('id')

    await update_subscription_status(paddle_subscription_id, {'status': 'paused'})
    await suspend_server(paddle_subscription_id)

async def handle_subscription_resumed(data: Dict[str, Any]):
    """Handle subscription resume after payment recovery"""
    print("=== SUBSCRIPTION RESUMED ===")

    subscription = data.get('data', {})
    paddle_subscription_id = subscription.get('id')

    await update_subscription_status(paddle_subscription_id, {
        'status': 'active',
        'next_billing_date': subscription.get('next_billed_at')
    })
    await resume_server(paddle_subscription_id)

async def handle_transaction_completed(data: Dict[str, Any]):
    """Handle successful payment for ongoing subscription"""
    print("=== TRANSACTION COMPLETED (Renewal Payment) ===")

    transaction = data.get('data', {})
    paddle_transaction_id = transaction.get('id')
    paddle_subscription_id = transaction.get('subscription_id')

    # Create transaction record for the payment
    await create_transaction_record({
        'paddle_transaction_id': paddle_transaction_id,
        'paddle_subscription_id': paddle_subscription_id,
        'amount': float(transaction.get('details', {}).get('totals', {}).get('grand_total', 0)) / 100,
        'description': f"Subscription renewal payment",
        'payment_method': transaction.get('payments', [{}])[0].get('method_details', {}).get('type'),
        'status': 'completed'
    })

    # Update subscription billing dates
    if paddle_subscription_id:
        await update_subscription_status(paddle_subscription_id, {
            'last_billing_date': datetime.now(),
            'status': 'active'  # Ensure it's active after successful payment
        })

async def handle_transaction_payment_failed(data: Dict[str, Any]):
    """Handle failed renewal payment"""
    print("=== PAYMENT FAILED (Renewal) ===")

    transaction = data.get('data', {})
    paddle_transaction_id = transaction.get('id')
    paddle_subscription_id = transaction.get('subscription_id')

    # Create failed transaction record
    await create_transaction_record({
        'paddle_transaction_id': paddle_transaction_id,
        'paddle_subscription_id': paddle_subscription_id,
        'amount': float(transaction.get('details', {}).get('totals', {}).get('grand_total', 0)) / 100,
        'description': f"Failed renewal payment",
        'payment_method': transaction.get('payments', [{}])[0].get('method_details', {}).get('type'),
        'status': 'failed'
    })

    # Note: Paddle will typically pause the subscription automatically after failed payments
    # The suspension will be handled by subscription.paused event

async def handle_subscription_trialing(data: Dict[str, Any]):
    """Handle trial subscriptions (if you want to track Paddle trials too)"""
    print("=== SUBSCRIPTION TRIALING ===")
    # This would only fire if you're using Paddle's built-in trials
    # Since you handle trials internally, you might not need this
    pass

# Event router - only handle events for PAID subscriptions
EVENT_HANDLERS = {
    'subscription.created': handle_subscription_created,
    'subscription.updated': handle_subscription_updated,
    'subscription.canceled': handle_subscription_canceled,
    'subscription.paused': handle_subscription_paused,
    'subscription.resumed': handle_subscription_resumed,
    'subscription.trialing': handle_subscription_trialing,  # Optional
    'transaction.completed': handle_transaction_completed,
    'transaction.payment_failed': handle_transaction_payment_failed,
}

@app.route("/p_hook", methods=["POST"])
async def p_hook():
    # 1. Verify signature
    raw_body = await request.get_data()
    paddle_request = QuartRequestAdapter(request, raw_body)

    try:
        integrity_check = Verifier().verify(
            paddle_request,
            Secret('your_webhook_secret_here')
        )
    except Exception as e:
        print(f"Signature verification failed: {e}")
        abort(403)

    # 2. Parse webhook data
    data = await request.get_json()
    event_type = data.get('event_type')

    print(f"Received Paddle webhook: {event_type}")
    pprint.pprint(data)

    # 3. Route to appropriate handler
    if event_type in EVENT_HANDLERS:
        try:
            await EVENT_HANDLERS[event_type](data)
            print(f"Successfully processed {event_type}")
        except Exception as e:
            print(f"Error processing {event_type}: {e}")
            # Return 500 to trigger Paddle retry
            abort(500)
    else:
        print(f"Unhandled event type: {event_type}")

    return "OK", 200

# Additional endpoint to check user trial status (for your frontend)
@app.route("/api/user/<user_id>/trial-status", methods=["GET"])
async def get_trial_status(user_id: str):
    """Check if user can still create free trial subscriptions"""
    has_used_trial = await user_has_used_free_trial(user_id, None)  # Check globally or per-plan

    return {
        "can_create_trial": not has_used_trial,
        "must_pay": has_used_trial
    }

