"""Stripe billing. Runs in STUB mode when STRIPE_SECRET_KEY is unset, so the
app works offline/in tests; with keys set it creates real Checkout sessions and
processes webhooks."""
from . import config

PRICE_FOR_TIER = {"plus": config.STRIPE_PRICE_PLUS, "pro": config.STRIPE_PRICE_PRO}
STUB = not bool(config.STRIPE_SECRET_KEY)


def _stripe():
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY
    return stripe


def create_checkout(user, tier: str) -> dict:
    if tier not in PRICE_FOR_TIER:
        raise ValueError("unknown tier")
    if STUB:
        # No keys configured — return a stub so the flow is testable end to end.
        return {"mode": "stub", "url": f"{config.PUBLIC_URL}/billing/stub-checkout?tier={tier}", "tier": tier}
    stripe = _stripe()
    customer = user.stripe_customer_id
    if not customer:
        customer = stripe.Customer.create(email=user.email).id
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer,
        line_items=[{"price": PRICE_FOR_TIER[tier], "quantity": 1}],
        success_url=f"{config.PUBLIC_URL}/?upgraded={tier}",
        cancel_url=f"{config.PUBLIC_URL}/?canceled=1",
        metadata={"user_id": user.id, "tier": tier},
    )
    return {"mode": "live", "url": session.url, "customer_id": customer}


def parse_webhook(payload: bytes, sig_header: str) -> dict:
    """Return {user_id, tier, status} from a Stripe event (verified if secret set)."""
    stripe = _stripe()
    if config.STRIPE_WEBHOOK_SECRET:
        event = stripe.Webhook.construct_event(payload, sig_header, config.STRIPE_WEBHOOK_SECRET)
    else:
        import json
        event = json.loads(payload)
    obj = event["data"]["object"]
    meta = obj.get("metadata", {}) or {}
    status = "active" if event["type"] in ("checkout.session.completed", "customer.subscription.updated") else obj.get("status")
    return {"user_id": meta.get("user_id"), "tier": meta.get("tier"), "status": status,
            "customer_id": obj.get("customer")}
