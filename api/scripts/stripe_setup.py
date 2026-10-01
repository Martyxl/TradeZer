"""Jednorázové založení Stripe produktů + cen pro Tradezer předplatné.

Spuštění (z adresáře api/, s nastaveným STRIPE_SECRET_KEY — TEST nebo LIVE klíč):
    STRIPE_SECRET_KEY=sk_test_... python scripts/stripe_setup.py

Je idempotentní: ceny hledá/zakládá podle `lookup_key`, takže opakované spuštění
nevytvoří duplikáty. Na konci vypíše blok env proměnných (STRIPE_PRICE_*), který
vložíš do Vercelu (backend projekt trade-zer) / lokálního .env.

Částky odpovídají web/lib/plans.ts: měsíční $5/$15/$49, roční = round(měs*12*0,85).
"""
import os
import sys

import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
if not stripe.api_key:
    sys.exit("Nastav STRIPE_SECRET_KEY (sk_test_... nebo sk_live_...).")

MODE = "LIVE" if stripe.api_key.startswith("sk_live_") else "TEST"

# tier → (název, měsíčně v centech, ročně v centech)
PLANS = {
    "trader": ("Tradezer Trader", 500, 5100),
    "pro": ("Tradezer Pro", 1500, 15300),
    "elite": ("Tradezer Elite", 4900, 50000),
}
CURRENCY = "usd"


def ensure_product(tier: str, name: str) -> str:
    """Najdi produkt podle metadata.tier, nebo ho založ."""
    for p in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        if p.get("metadata", {}).get("tz_tier") == tier:
            return p["id"]
    prod = stripe.Product.create(name=name, metadata={"tz_tier": tier})
    print(f"  + produkt {name} ({prod['id']})")
    return prod["id"]


def ensure_price(product_id: str, tier: str, interval: str, amount: int) -> str:
    """Najdi cenu podle lookup_key, nebo ji založ."""
    lookup = f"tz_{tier}_{interval}"  # month|year → tz_trader_month …
    existing = stripe.Price.list(lookup_keys=[lookup], limit=1).get("data", [])
    if existing:
        return existing[0]["id"]
    price = stripe.Price.create(
        product=product_id,
        unit_amount=amount,
        currency=CURRENCY,
        recurring={"interval": interval},
        lookup_key=lookup,
        metadata={"tz_tier": tier},
    )
    print(f"  + cena {lookup} = ${amount/100:.2f}/{interval} ({price['id']})")
    return price["id"]


def main() -> None:
    print(f"Stripe setup — režim {MODE}\n")
    env_lines = []
    for tier, (name, m_amount, y_amount) in PLANS.items():
        print(f"{name}:")
        product_id = ensure_product(tier, name)
        m_id = ensure_price(product_id, tier, "month", m_amount)
        y_id = ensure_price(product_id, tier, "year", y_amount)
        env_lines.append(f"STRIPE_PRICE_{tier.upper()}_MONTH={m_id}")
        env_lines.append(f"STRIPE_PRICE_{tier.upper()}_YEAR={y_id}")

    print("\n=== Vlož do env (Vercel backend trade-zer + lokální api/.env) ===")
    print("\n".join(env_lines))


if __name__ == "__main__":
    main()
