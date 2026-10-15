"""Právní konstanty — verze podmínek, na kterých uživatel souhlasil při registraci.

Při jakékoli věcné změně Obchodních podmínek nebo Zásad ochrany osobních údajů ZVYŠ
`TERMS_VERSION` (datum účinnosti) i v `web/lib/legal.ts` — registrace ji ukládá k uživateli
(důkaz, s čím souhlasil).
"""
TERMS_VERSION = "2026-10-15"

# Text zobrazený na platební stránce Stripe Checkout pod tlačítkem (podporuje markdown odkazy).
# Dává spotřebiteli informaci o právu na odstoupení a žádost o okamžité zahájení služby.
CHECKOUT_SUBMIT_MESSAGE = (
    "Kliknutím souhlasíš s [Obchodními podmínkami](https://tradezer.app/obchodni-podminky) a "
    "[Zásadami ochrany osobních údajů](https://tradezer.app/ochrana-osobnich-udaju). "
    "Výslovně žádáš o **okamžité zahájení poskytování služby** před uplynutím 14denní lhůty pro odstoupení. "
    "Odstoupíš-li, uhradíš poměrnou část ceny za dobu, po kterou byla služba poskytována."
)
