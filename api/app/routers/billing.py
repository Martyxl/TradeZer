"""Stripe Billing — předplatné (Checkout → webhook → user.plan).

Tok: frontend zavolá /checkout → přesměruje uživatele na hostovaný Stripe Checkout
→ po zaplacení Stripe pošle webhook → nastavíme user.plan podle zakoupeného price.
Paywall gating (require_plan) pak zbytek zařídí sám. Žádné Connect, žádné karty
na našem serveru (PCI řeší Stripe). Stripe Tax (automatic_tax) kvůli EU VAT.

Chybějící/nenakonfigurovaný Stripe → 503 (nikdy neshodí zbytek backendu)."""
from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.db.session import session_context
from app.models import User
from app.routers.auth import current_user, VALID_PLANS

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/billing", tags=["billing"])

_INTERVALS = ("month", "year")


def _require_stripe():
    """Vrátí nakonfigurovaný stripe modul, nebo 503 když chybí klíč/lib."""
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Platby nejsou nakonfigurované")
    try:
        import stripe
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=503, detail="Stripe knihovna není nainstalovaná")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _price_map() -> dict[tuple[str, str], str]:
    s = settings
    return {
        ("trader", "month"): s.stripe_price_trader_month,
        ("trader", "year"): s.stripe_price_trader_year,
        ("pro", "month"): s.stripe_price_pro_month,
        ("pro", "year"): s.stripe_price_pro_year,
        ("elite", "month"): s.stripe_price_elite_month,
        ("elite", "year"): s.stripe_price_elite_year,
    }


def _price_to_tier() -> dict[str, str]:
    """Reverzní mapa price_id → tier (pro webhook). Prázdné price přeskočí."""
    return {price: tier for (tier, _interval), price in _price_map().items() if price}


@router.get("/config")
async def billing_config():
    """Veřejné: publishable key + které tiery mají nastavený price (lze koupit)."""
    pm = _price_map()
    prices = {}
    for (tier, interval), price in pm.items():
        if price:
            prices.setdefault(tier, {})[interval] = True
    return {
        "enabled": bool(settings.stripe_secret_key),
        "publishable_key": settings.stripe_publishable_key,
        "buyable": prices,  # {tier: {month: true, year: true}}
    }


@router.post("/checkout")
async def create_checkout(
    payload: dict,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Založí Stripe Checkout session pro předplatné (tier × interval) a vrátí URL."""
    stripe = _require_stripe()
    tier = (payload.get("tier") or "").strip().lower()
    interval = (payload.get("interval") or "month").strip().lower()
    if tier not in ("trader", "pro", "elite"):
        raise HTTPException(status_code=400, detail="Neplatný tier")
    if interval not in _INTERVALS:
        raise HTTPException(status_code=400, detail="Neplatný interval")
    price_id = _price_map().get((tier, interval))
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Pro {tier}/{interval} není nastavený price")

    # Zajisti Stripe zákazníka (1:1 s účtem) — ať se historie plateb drží u usera.
    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.email or None,
            metadata={"user_id": str(user.id), "username": user.username or ""},
        )
        customer_id = customer["id"]
        user.stripe_customer_id = customer_id
        await session.commit()

    base = settings.app_public_url.rstrip("/")
    params = dict(
        mode="subscription",
        customer=customer_id,
        client_reference_id=str(user.id),
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base}/predplatne?checkout=success",
        cancel_url=f"{base}/predplatne?checkout=cancel",
        allow_promotion_codes=True,
        metadata={"user_id": str(user.id), "tier": tier},
        subscription_data={"metadata": {"user_id": str(user.id), "tier": tier}},
    )
    if settings.stripe_tax_enabled:
        # Vyžaduje aktivovaný Stripe Tax + origin adresu v dashboardu.
        params["automatic_tax"] = {"enabled": True}
        params["customer_update"] = {"address": "auto", "name": "auto"}
    try:
        cs = stripe.checkout.Session.create(**params)
    except Exception as e:  # noqa: BLE001
        log.error("Stripe checkout failed", error=str(e), user_id=user.id)
        raise HTTPException(status_code=502, detail="Chyba při zakládání platby")
    return {"url": cs["url"]}


@router.post("/portal")
async def create_portal(
    user: User = Depends(current_user),
):
    """Billing Portal — self-service správa předplatného (změna/zrušení, faktury)."""
    stripe = _require_stripe()
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Účet nemá žádné předplatné")
    base = settings.app_public_url.rstrip("/")
    try:
        ps = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{base}/ucet",
        )
    except Exception as e:  # noqa: BLE001
        log.error("Stripe portal failed", error=str(e), user_id=user.id)
        raise HTTPException(status_code=502, detail="Chyba při otevírání správy předplatného")
    return {"url": ps["url"]}


# ── Webhook ─────────────────────────────────────────────────────────────────
def _period_end(sub: dict) -> datetime | None:
    ts = sub.get("current_period_end")
    return datetime.utcfromtimestamp(ts) if ts else None


def _tier_from_subscription(sub: dict) -> str | None:
    """Z aktivního subscription vyčte price → tier (dle reverzní mapy)."""
    try:
        price_id = sub["items"]["data"][0]["price"]["id"]
    except (KeyError, IndexError, TypeError):
        return None
    return _price_to_tier().get(price_id)


async def _apply_subscription(stripe, customer_id: str, sub: dict, *, reference_user_id: str | None = None) -> None:
    """Promítne stav subscription do user.plan/status/period (idempotentní)."""
    status = sub.get("status")
    tier = _tier_from_subscription(sub)
    # Aktivní/trialing = dej tier; jinak (canceled/unpaid/…) spadni na free.
    active = status in ("active", "trialing", "past_due")
    new_plan = tier if (active and tier) else "free"
    if new_plan not in VALID_PLANS:
        new_plan = "free"

    async with session_context() as session:
        user = None
        if reference_user_id:
            user = await session.get(User, int(reference_user_id))
        if user is None:
            user = await session.scalar(
                select(User).where(User.stripe_customer_id == customer_id)
            )
        if user is None:
            log.warning("Webhook: user nenalezen", customer=customer_id)
            return
        # Admina nikdy neshazuj na free kvůli Stripe stavu (má bypass).
        if user.is_admin and new_plan == "free":
            new_plan = user.plan
        user.stripe_customer_id = customer_id
        user.subscription_status = status
        user.subscription_period_end = _period_end(sub)
        user.plan = new_plan
        await session.commit()
        log.info("Webhook: plán aktualizován", user_id=user.id, plan=new_plan, status=status)


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Přijímá Stripe události (ověřený podpis) a drží user.plan v souladu se Stripe.
    Míří přímo na backend (ne přes Next proxy) kvůli surovému tělu pro podpis."""
    stripe = _require_stripe()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret není nastaven")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except Exception as e:  # noqa: BLE001 — špatný podpis / neplatné tělo
        log.warning("Webhook: neplatný podpis", error=str(e))
        raise HTTPException(status_code=400, detail="Neplatný podpis")

    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        customer_id = obj.get("customer")
        sub_id = obj.get("subscription")
        ref = obj.get("client_reference_id")
        if sub_id and customer_id:
            sub = stripe.Subscription.retrieve(sub_id)
            await _apply_subscription(stripe, customer_id, sub, reference_user_id=ref)
    elif etype in ("customer.subscription.updated", "customer.subscription.created",
                   "customer.subscription.deleted"):
        customer_id = obj.get("customer")
        if customer_id:
            await _apply_subscription(stripe, customer_id, obj)
    else:
        log.debug("Webhook: ignorovaná událost", type=etype)

    return {"received": True}
