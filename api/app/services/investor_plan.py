"""Jednoduchý režim (Začátečník): investiční plány, třídění pozic do tříd aktiv a pravidla,
ze kterých vzniká seznam „Co teď udělat".

Vše je čistě pravidlové a transparentní — signál vždy říká PROČ (odchylka od vlastního plánu
uživatele, semafor pozice, daňový test). Není to investiční doporučení; plán si volí uživatel.
Čisté funkce bez DB → snadno testovatelné (api/tests/test_investor.py).
"""
from __future__ import annotations

import math
import re

from app.valuation.zones import zone, zone_reliability, zone_score

# ── Třídy aktiv a plány ─────────────────────────────────────────────────────
CLASSES: dict[str, str] = {
    "world": "Akciové fondy (ETF)",
    "bonds": "Dluhopisy",
    "gold": "Zlato",
    "cash": "Rezerva",
    "stocks": "Vlastní akcie",
}
CLASS_ORDER = ["world", "bonds", "gold", "cash", "stocks"]

PLANS: dict[str, dict] = {
    "careful": {"label": "Opatrný", "targets": {"world": 40, "bonds": 35, "gold": 15, "cash": 10, "stocks": 0},
                "for": "Chceš klidný spánek a menší výkyvy. Vhodné, pokud budeš peníze potřebovat do 3–5 let."},
    "balanced": {"label": "Vyvážený", "targets": {"world": 60, "bonds": 15, "gold": 10, "cash": 0, "stocks": 15},
                 "for": "Investuješ na 5–10 let a propad o třetinu přečkáš bez prodeje."},
    "bold": {"label": "Dynamický", "targets": {"world": 65, "bonds": 0, "gold": 5, "cash": 0, "stocks": 30},
             "for": "Horizont přes 10 let, velké výkyvy tě nerozhodí a chceš vybírat i jednotlivé firmy."},
    "aggressive": {"label": "Agresivní", "targets": {"world": 55, "bonds": 0, "gold": 0, "cash": 0, "stocks": 45},
                   "for": "Jde ti o maximální růst. Propad o polovinu přečkáš a firmy si aktivně vybíráš. Bez dluhopisů a zlata."},
}
DEFAULT_PLAN = "balanced"

# Bezpečný základ — široké UCITS fondy obchodované na Xetře (EUR), dostupné u XTB i eToro.
# TER orientačně (ověř v KID fondu). `default` = výchozí nástroj své třídy v nákupním plánu.
UNIVERSE: list[dict] = [
    {"symbol": "VWCE.DE", "short": "VWCE", "cls": "world", "default": True, "ter": 0.19, "currency": "EUR",
     "name": "Vanguard FTSE All-World UCITS ETF (Acc)",
     "what": "Celý svět v jednom fondu — přes 3 500 firem z vyspělých i rozvíjejících se zemí.",
     "role": "Jádro portfolia. Kdo nechce nic řešit, vystačí si s ním."},
    {"symbol": "SXR8.DE", "short": "SXR8", "cls": "world", "ter": 0.07, "currency": "EUR",
     "name": "iShares Core S&P 500 UCITS ETF (Acc)",
     "what": "500 největších firem v USA.", "role": "Levná alternativa jádra, jen USA (vyšší koncentrace)."},
    {"symbol": "EUNL.DE", "short": "EUNL", "cls": "world", "ter": 0.20, "currency": "EUR",
     "name": "iShares Core MSCI World UCITS ETF (Acc)",
     "what": "Asi 1 400 firem z vyspělých zemí.", "role": "Jádro bez rozvíjejících se trhů."},
    {"symbol": "IS3N.DE", "short": "IS3N", "cls": "world", "ter": 0.18, "currency": "EUR",
     "name": "iShares Core MSCI EM IMI UCITS ETF (Acc)",
     "what": "Rozvíjející se trhy — Čína, Indie, Tchaj-wan, Brazílie…", "role": "Doplněk k MSCI World (cca 10–15 %)."},
    {"symbol": "4GLD.DE", "short": "4GLD", "cls": "gold", "default": True, "ter": 0.30, "currency": "EUR",
     "name": "Xetra-Gold (ETC)",
     "what": "Fyzické zlato v trezoru, 1 kus ≈ 1 gram.", "role": "Pojistka v krizích a proti inflaci."},
    {"symbol": "EUNA.DE", "short": "EUNA", "cls": "bonds", "default": True, "ter": 0.10, "currency": "EUR",
     "name": "iShares Core Global Aggregate Bond UCITS ETF EUR Hedged (Acc)",
     "what": "Státní a firemní dluhopisy z celého světa, měnově zajištěné do EUR.", "role": "Stabilizátor — tlumí propady akcií."},
    {"symbol": "XEON.DE", "short": "XEON", "cls": "cash", "default": True, "ter": 0.10, "currency": "EUR",
     "name": "Xtrackers II EUR Overnight Rate Swap UCITS ETF 1C",
     "what": "Peněžní trh — úrok podle sazby ECB, téměř bez výkyvů.", "role": "Rezerva s úrokem (alternativa spořicího účtu)."},
]
UNIVERSE_BY_SYMBOL = {u["symbol"]: u for u in UNIVERSE}
DEFAULT_INSTRUMENT = {u["cls"]: u for u in UNIVERSE if u.get("default")}

# Známé fondy podle tickeru bez burzovního suffixu (XTB/eToro/Yahoo zápisy se liší jen suffixem).
_ALIASES: dict[str, set[str]] = {
    "world": {"VWCE", "VWRL", "VWRA", "VWRP", "IWDA", "SWDA", "EUNL", "CSPX", "SXR8", "SPYL", "VUSA", "VUAA", "SPY",
              "VOO", "IVV", "VTI", "QQQ", "QQQM", "EQQQ", "CNDX", "SXRV", "IS3N", "EIMI", "XDWD", "XMME", "SPPW",
              "IUSQ", "ACWI", "VT", "VEA", "VWO", "SSAC", "XDEW", "ZPRV", "ZPRX", "MEUD", "VEUR", "VGWL", "KWBE",
              "SPXS", "XDEM", "IUSN", "WSML", "SMEA", "IMEU", "XDAX", "EXS1", "CEMR"},
    "bonds": {"EUNA", "AGGH", "AGGG", "IBCI", "IEAG", "VAGF", "VGEA", "BND", "AGG", "TLT", "IEF", "SHY", "IBTA",
              "IBTS", "EUN5", "VGOV", "IGLT", "XGLE", "DBXN", "EXX6", "SXRL", "BNDX", "GOVT", "VAGS", "IBGS"},
    "gold": {"4GLD", "IGLN", "SGLN", "PHAU", "SGLD", "EGLN", "GLD", "IAU", "GLDM", "XAD5", "EWG2", "GZUR", "8PSG",
             "XAUUSD", "GOLD.CMD"},
    "cash": {"XEON", "CSH2", "ERNE", "ERNX", "BIL", "SGOV", "SHV", "LQDE", "XEOD", "SMART"},
}
_ALIAS_TO_CLASS = {s: c for c, syms in _ALIASES.items() for s in syms}

_RE_BOND = re.compile(r"bond|treasur|aggregate|govt|government|corporate|dluhopis|t-bill|gilt", re.I)
_RE_GOLD = re.compile(r"\bgold\b|zlat", re.I)
_RE_CASH = re.compile(r"overnight|money market|€str|estr|cash\b|ultrashort|ultra short", re.I)
_RE_FUND = re.compile(r"\betf\b|\betc\b|ucits|\bindex\b|fund\b", re.I)


def base_symbol(symbol: str) -> str:
    return (symbol or "").upper().split(".")[0]


def classify(symbol: str, name: str | None = None, meta: dict | None = None) -> str:
    """Třída aktiva pro pozici: známý ticker → podle seznamu; jinak podle typu z metadat / názvu fondu."""
    s = (symbol or "").upper()
    if s in UNIVERSE_BY_SYMBOL:
        return UNIVERSE_BY_SYMBOL[s]["cls"]
    if s in _ALIAS_TO_CLASS:
        return _ALIAS_TO_CLASS[s]
    b = base_symbol(s)
    if b in _ALIAS_TO_CLASS:
        return _ALIAS_TO_CLASS[b]
    nm = name or ""
    is_fund = (meta or {}).get("type", "").upper() in ("ETF", "ETC", "FUND") or bool(_RE_FUND.search(nm))
    if is_fund:
        if _RE_GOLD.search(nm):
            return "gold"
        if _RE_CASH.search(nm):
            return "cash"
        if _RE_BOND.search(nm):
            return "bonds"
        return "world"
    return "stocks"


def plan_targets(plan: str, custom: dict | None = None) -> dict[str, float]:
    """Cílové váhy tříd (součet 100). Vlastní plán se normalizuje; neznámý plán → výchozí."""
    if plan == "custom" and custom:
        clean = {c: max(0.0, float(custom.get(c) or 0)) for c in CLASS_ORDER}
        total = sum(clean.values())
        if total > 0:
            return {c: round(v / total * 100, 2) for c, v in clean.items()}
    return dict(PLANS.get(plan, PLANS[DEFAULT_PLAN])["targets"])


def validate_custom(targets: dict) -> dict[str, float]:
    if not isinstance(targets, dict):
        raise ValueError("targets musí být objekt {třída: %}")
    out = {}
    for c in CLASS_ORDER:
        v = targets.get(c, 0)
        try:
            v = float(v or 0)
        except (TypeError, ValueError):
            raise ValueError(f"neplatná hodnota pro {c}")
        if v < 0 or v > 100 or math.isnan(v):
            raise ValueError(f"{c}: 0–100 %")
        out[c] = v
    if abs(sum(out.values()) - 100) > 0.5:
        raise ValueError("součet cílových vah musí být 100 %")
    return out


# ── Rozložení a měsíční nákupní plán ────────────────────────────────────────
def allocation(positions: list[dict], targets: dict[str, float], reserve: float = 0.0) -> dict:
    """positions: [{symbol, cls, value_base}] → rozložení po třídách vs. cíl.
    Rezerva mimo brokera se počítá do třídy „cash“. Pozice bez ceny se nezapočítají (`unpriced`)."""
    by = {c: 0.0 for c in CLASS_ORDER}
    unpriced = []
    for p in positions:
        if p.get("value_base") is None:
            unpriced.append(p["symbol"])
            continue
        by[p["cls"]] += p["value_base"]
    by["cash"] += max(0.0, reserve or 0.0)
    total = sum(by.values())
    rows = []
    for c in CLASS_ORDER:
        pct = (by[c] / total * 100) if total else 0.0
        t = targets.get(c, 0)
        if t == 0 and by[c] == 0:
            continue
        rows.append({"cls": c, "label": CLASSES[c], "value": round(by[c], 2), "pct": round(pct, 1),
                     "target": t, "diff": round(pct - t, 1)})
    return {"total": round(total, 2), "classes": rows, "unpriced": unpriced}


MIN_ORDER_CZK = 500  # menší nákup nedává smysl (víc položek, víc práce) → přičte se k největšímu


def split_contribution(alloc: dict, targets: dict[str, float], monthly: float, step: float = 100,
                       min_order: float = MIN_ORDER_CZK) -> dict[str, float]:
    """Rozdělí částku k investování (měsíční vklad + volné peníze) tak, aby dorovnávala podváhové třídy
    (rebalancování vkladem, bez prodeje). Nejdřív se zaplní mezery k cíli; co zbude, jde podle cílových vah.
    Zaokrouhleno na `step`; položky pod `min_order` se přičtou k největší (malý vklad = méně nákupů)."""
    if monthly <= 0:
        return {}
    cur = {r["cls"]: r["value"] for r in alloc["classes"]}
    new_total = alloc["total"] + monthly
    gaps = {c: max(0.0, targets.get(c, 0) / 100 * new_total - cur.get(c, 0.0)) for c in CLASS_ORDER if targets.get(c, 0) > 0}
    gap_sum = sum(gaps.values())
    raw: dict[str, float] = {}
    if gap_sum >= monthly and gap_sum > 0:
        raw = {c: monthly * g / gap_sum for c, g in gaps.items()}
    else:
        rest = monthly - gap_sum
        tsum = sum(targets.get(c, 0) for c in gaps) or 1
        raw = {c: g + rest * targets.get(c, 0) / tsum for c, g in gaps.items()}
    out = {c: round(v / step) * step for c, v in raw.items()}
    # dorovnání zaokrouhlení do největší položky, ať součet sedí na vklad
    diff = round(monthly / step) * step - sum(out.values())
    if out and diff:
        k = max(out, key=lambda c: raw[c])
        out[k] += diff
    small = [c for c, v in out.items() if 0 < v < min_order]
    big = [c for c, v in out.items() if v >= min_order]
    if small and big:
        k = max(big, key=lambda c: out[c])
        for c in small:
            out[k] += out.pop(c)
    return {c: v for c, v in out.items() if v >= step}


def capital_hint(capital_left: float, monthly: float, regime_state: str | None) -> str | None:
    """Rada k větší jednorázové částce: najednou, nebo rozložit do několika nákupů."""
    if capital_left < max(20_000, 3 * (monthly or 0)):
        return None
    if regime_state in ("tension", "panic"):
        return (f"Volných {_fmt_czk(capital_left)} je hodně najednou a trh je teď nervózní. Klidně je rozlož "
                "do 3 nákupů s odstupem pár týdnů — když trh mezitím spadne, koupíš levněji.")
    return (f"Volných {_fmt_czk(capital_left)} můžeš investovat najednou (historicky to častěji vycházelo líp), "
            "nebo je rozložit do 3–6 měsíčních nákupů, pokud tě znervózňuje, že koupíš těsně před propadem.")


# ── Texty k režimu trhu a sentimentu ────────────────────────────────────────
REGIME_TIPS = {
    "calm": ("Klid", "Normální podmínky. Pokračuj podle plánu."),
    "recovering": ("Stabilizace", "Trh se zotavuje po výkyvu. Pokračuj podle plánu, nic nedoháněj."),
    "tension": ("Napětí", "Trh je nervózní. Pravidelné nákupy nepřerušuj, větší jednorázové nákupy rozděl do 2–3 částí."),
    "panic": ("Panika", "Neprodávej ve strachu. Po propadech se historicky vyplatilo v nákupech pokračovat — jen ne na dluh."),
}


def sentiment_tip(score: float | None) -> tuple[str, str] | None:
    if score is None:
        return None
    if score < 25:
        return "extrémní strach", "Ostatní se bojí. Takové chvíle bývaly dobré na nákup — drž se plánu a neprodávej."
    if score < 45:
        return "strach", "Opatrná nálada. Pravidelný nákup teď vychází levněji než obvykle."
    if score < 55:
        return "neutrální", "Nálada bez extrémů. Pokračuj podle plánu."
    if score < 75:
        return "chamtivost", "Trh je optimistický. Nenaskakuj do drahých akcií, drž se plánu."
    return "extrémní chamtivost", "Euforie. Nepřikupuj drahé akcie a zkontroluj, jestli nejsi nad cílem u akcií."


def market_block(regime: dict | None) -> dict:
    r = regime or {}
    st = r.get("state")
    label, tip = REGIME_TIPS.get(st, (None, None))
    sent = r.get("sentiment") or {}
    score = sent.get("score")
    s_tip = sentiment_tip(score)
    return {
        "regime": {"state": st, "label": label or r.get("label"), "tip": tip, "as_of": r.get("as_of")} if st else None,
        "sentiment": {"score": round(score) if score is not None else None, "label": s_tip[0], "tip": s_tip[1],
                      "as_of": sent.get("as_of_date")} if s_tip else None,
    }


# ── Seznam akcí „Co teď udělat" ─────────────────────────────────────────────
TAX_WAIT_DAYS = 90      # červená pozice, která bude do 90 dnů bez daně → „počkej"
TAX_SOON_DAYS = 30      # upozornit na blížící se osvobození
CONCENTRATION_PCT = 20  # jedna akcie nad 20 % portfolia → zvážit snížení
CLASS_OVER_PP = 10      # třída nad cílem o víc než 10 p.b. → upozornění


def _fmt_czk(v: float) -> str:
    return f"{round(v):,}".replace(",", " ") + " Kč"


def _date_cs(iso: str) -> str:
    y, m, d = iso[:10].split("-")
    return f"{int(d)}. {int(m)}. {y}"


SMALL_PORTFOLIO_CZK = 50_000  # menší portfolio: část pro vlastní akcie jde do širokého fondu
STOCK_PICK_CZK = 25_000       # větší nákup akcií se rozdělí mezi víc firem (max 3)


def fit_to_size(contribution: dict[str, float], total_after: float) -> tuple[dict[str, float], bool]:
    """U malého portfolia nedávají jednotlivé firmy smysl (jedna by měla desítky %) → jejich díl dostane
    akciový fond. Vrací (upravené rozdělení, zda se akcie odložily)."""
    if total_after >= SMALL_PORTFOLIO_CZK or not contribution.get("stocks"):
        return contribution, False
    out = dict(contribution)
    out["world"] = out.get("world", 0) + out.pop("stocks")
    return {c: out[c] for c in CLASS_ORDER if out.get(c)}, True


def stock_picks(positions: list[dict], ideas: list[dict], amt: float, step: float = 100) -> list[tuple]:
    """Komu dát peníze na vlastní akcie: nejdřív držené se zeleným semaforem (pod 10 % portfolia),
    pak levné kvalitní firmy z Nápadů, které ještě nedrží. Větší částka → až 3 firmy.
    Výstup: [(symbol, název, částka, proč)]."""
    green = sorted((p for p in positions if p["cls"] == "stocks" and (p.get("signal") or {}).get("color") == "green"
                    and (p.get("weight") or 0) < 10), key=lambda p: p.get("weight") or 0)
    held = {base_symbol(p["symbol"]) for p in positions}
    cands = [(p["symbol"], p.get("name"), "Máš ji v portfoliu a vychází levně (zelený semafor).") for p in green]
    cands += [(i["ticker"], i.get("name"), "Levná kvalitní firma z Nápadů — klidně ji vyměň za jinou odtud.")
              for i in ideas if base_symbol(i["ticker"]) not in held]
    if not cands:
        return []
    n = max(1, min(3, len(cands), math.ceil(amt / STOCK_PICK_CZK)))
    part = math.floor(amt / n / step) * step
    parts = [part] * (n - 1) + [amt - part * (n - 1)]
    return [(s, nm, a, why) for (s, nm, why), a in zip(cands[:n], parts)]


def build_actions(*, positions: list[dict], alloc: dict, targets: dict[str, float], contribution: dict[str, float],
                  lots: list[dict], ideas: list[dict], prices_czk: dict[str, float],
                  stocks_deferred: bool = False) -> list[dict]:
    """positions: [{symbol, name, cls, value_base, weight, signal{color,reasons,trim_qty,action}, unrealized_pct}]
    lots: z daňového testu ({symbol, days_remaining, free_date, tax_free}); ideas: levné firmy z Nápadů.
    Výstup seřazený podle důležitosti: buy → trim/wait → rebalance → tax → hold."""
    actions: list[dict] = []
    by_cls = {r["cls"]: r for r in alloc["classes"]}
    held = {p["symbol"]: p for p in positions}
    lots_by: dict[str, list[dict]] = {}
    for lt in lots:
        lots_by.setdefault(lt["symbol"], []).append(lt)

    # 1) Nákupy z měsíčního vkladu
    for c in CLASS_ORDER:
        amt = contribution.get(c)
        if not amt:
            continue
        row = by_cls.get(c, {"pct": 0.0, "target": targets.get(c, 0)})
        why = f"{CLASSES[c]} tvoří {row['pct']:.0f} % portfolia, cíl je {row['target']:.0f} %." if alloc["total"] else \
            f"Začátek plánu — {CLASSES[c].lower()} má mít {row['target']:.0f} %."
        if c == "stocks":
            picks = stock_picks(positions, ideas, amt)
            if not picks:
                actions.append({"kind": "buy", "symbol": None, "name": None, "cls": c, "amount": amt, "units": None,
                                "title": f"Koupit vlastní akcie za {_fmt_czk(amt)}",
                                "text": f"{why} Vyber firmu v Nápadech (sekce Levné kvalitní firmy). Jedna firma max 10 % portfolia."})
                continue
            split = "" if len(picks) == 1 else f" Částku {_fmt_czk(amt)} jsme rozdělili mezi {len(picks)} firmy, ať nevsadíš vše na jednu."
            for sym, name, part, extra in picks:
                units = round(part / prices_czk[sym], 2) if prices_czk.get(sym) else None
                actions.append({"kind": "buy", "symbol": sym, "name": name, "cls": c, "amount": part, "units": units,
                                "title": f"Koupit {base_symbol(sym)} za {_fmt_czk(part)}",
                                "text": " ".join(x for x in (why, extra, split.strip()) if x)})
            continue
        else:
            own = sorted((p for p in positions if p["cls"] == c and p.get("value_base")), key=lambda p: -p["value_base"])
            inst = DEFAULT_INSTRUMENT.get(c)
            sym = own[0]["symbol"] if own else (inst["symbol"] if inst else None)
            name = own[0].get("name") if own else (inst["name"] if inst else None)
            extra = "Pokračuj ve fondu, který už máš." if own else ("Hotovost můžeš nechat i na spořicím účtu." if c == "cash" else "")
            if c == "world" and stocks_deferred:
                extra = (extra + " Obsahuje i část pro vlastní akcie — jednotlivé firmy přidej, až portfolio přeroste "
                          f"{_fmt_czk(SMALL_PORTFOLIO_CZK)}. Do té doby je široký fond bezpečnější.").strip()
        units = None
        if sym and prices_czk.get(sym):
            units = round(amt / prices_czk[sym], 2)
        actions.append({"kind": "buy", "symbol": sym, "name": name, "cls": c, "amount": amt, "units": units,
                        "title": f"Koupit {base_symbol(sym) if sym else CLASSES[c].lower()} za {_fmt_czk(amt)}",
                        "text": " ".join(x for x in (why, extra) if x)})

    # 2) Pozice k ořezu / počkat kvůli dani (jen jednotlivé akcie — fondy srovná rebalancování)
    flagged = set()
    for p in positions:
        if p["cls"] != "stocks":
            continue
        sig = p.get("signal") or {}
        w = p.get("weight") or 0
        red = sig.get("color") == "red"
        conc = w >= CONCENTRATION_PCT
        if not (red or conc):
            continue
        flagged.add(p["symbol"])
        my_lots = lots_by.get(p["symbol"], [])
        soon = sorted((lt for lt in my_lots if 0 < lt["days_remaining"] <= TAX_WAIT_DAYS), key=lambda lt: lt["days_remaining"])
        all_free = bool(my_lots) and all(lt["tax_free"] for lt in my_lots)
        reasons = list(sig.get("reasons") or [])
        if conc and not any("váha" in r for r in reasons):
            reasons.insert(0, f"tvoří {w:.0f} % portfolia")
        trim = sig.get("trim_qty")
        if trim is None and w > 10 and p.get("quantity"):
            trim = round(p["quantity"] * (1 - 10.0 / w), 4)
        if trim:
            trim = round(trim) if trim >= 10 else round(trim, 2)
        what = f"Prodej ~{trim:g} ks vrátí váhu k 10 %." if trim else "Zvaž prodej části zisku."
        if soon and (p.get("unrealized_pct") or 0) > 0:
            lt = soon[0]
            actions.append({"kind": "wait", "symbol": p["symbol"], "name": p.get("name"), "cls": "stocks",
                            "title": f"Počkej s prodejem {base_symbol(p['symbol'])} do {_date_cs(lt['free_date'])}",
                            "text": f"Je důvod ubrat ({', '.join(reasons)}), ale za {lt['days_remaining']} dní bude "
                                    f"nákup osvobozen od daně. Pak: {what}"})
        else:
            tax = " Prodej je už bez daně (drženo přes 3 roky)." if all_free else \
                (" Zisk z prodeje se bude danit (drženo méně než 3 roky)." if my_lots else "")
            actions.append({"kind": "trim", "symbol": p["symbol"], "name": p.get("name"), "cls": "stocks", "qty": trim,
                            "title": f"Zvážit prodej části {base_symbol(p['symbol'])}",
                            "text": f"{', '.join(reasons).capitalize()}. {what}{tax}"})

    # 3) Třída výrazně nad cílem
    for r in alloc["classes"]:
        if r["diff"] > CLASS_OVER_PP and alloc["total"]:
            text = ("Tvůj plán s touto částí nepočítá. Nepřikupuj; jestli ji chceš opustit, prodávej postupně "
                    "a nejdřív to, co je už bez daně.") if not r["target"] else                 ("Do této části teď nepřikupuj — vklady půjdou jinam a podíl se postupně srovná. "
                 "Chceš-li srovnat hned, prodej část; nejdřív to, co je už bez daně.")
            actions.append({"kind": "rebalance", "symbol": None, "cls": r["cls"],
                            "title": f"{r['label']} nad plánem ({r['pct']:.0f} % místo {r['target']:.0f} %)",
                            "text": text})

    # 4) Blížící se osvobození od daně (informace)
    seen = set()
    for lt in sorted(lots, key=lambda x: x["days_remaining"]):
        if not (0 < lt["days_remaining"] <= TAX_SOON_DAYS) or lt["symbol"] in flagged or lt["symbol"] in seen:
            continue
        seen.add(lt["symbol"])
        actions.append({"kind": "tax", "symbol": lt["symbol"], "name": lt.get("name"),
                        "title": f"{base_symbol(lt['symbol'])}: bez daně od {_date_cs(lt['free_date'])}",
                        "text": f"Za {lt['days_remaining']} dní uplynou 3 roky od nákupu. Pokud zvažuješ prodej, "
                                "počkej do tohoto data."})
        if len(seen) >= 3:
            break

    # 5) Zbytek: nic nedělat
    rest = [p for p in positions if p["symbol"] not in flagged]
    if rest:
        actions.append({"kind": "hold", "symbol": None, "count": len(rest),
                        "title": f"Ostatní pozice ({len(rest)}): držet",
                        "text": "Nic dělat nemusíš. Investování je hlavně o trpělivosti."})
    return actions


# ── Nápady z Valuation Radaru ───────────────────────────────────────────────
def _idea_text(it: dict) -> str:
    pct, g = it.get("pctile_pe_fwd"), it.get("eps_growth_ntm")
    parts = []
    if pct is not None:
        parts.append("levnější než obvykle" if pct <= 35 else "cena kolem svého průměru" if pct <= 65 else "dražší než obvykle")
    if g is not None:
        parts.append(f"zisky rostou ~{g:.0f} % ročně" if g >= 0 else f"zisky klesají ({g:.0f} %)")
    return ", ".join(parts).capitalize()


def ideas_from_overview(rows: list[dict], *, held: set[str] | None = None,
                        fund_buyers: dict[str, int] | None = None, house: set[str] | None = None,
                        limit: int = 8) -> dict:
    """Z předpočteného overview: levné kvalitní firmy (nákupní zóna, spolehlivá data) a předražené (pozor)."""
    held = held or set()
    fund_buyers = fund_buyers or {}
    house = house or set()

    def enrich(it: dict, kind: str) -> dict:
        t = (it.get("ticker") or "").upper()
        tags = []
        if fund_buyers.get(t):
            tags.append(f"přikupují fondy ({fund_buyers[t]})")
        if t in house:
            tags.append("drží Tradezer fond")
        if t in held:
            tags.append("máš v portfoliu")
        return {"ticker": t, "name": it.get("name"), "verdict": it.get("valuation_verdict"), "kind": kind,
                "text": _idea_text(it), "tags": tags, "score": it.get("composite_score"),
                "market_cap": it.get("market_cap")}

    cheap, rich = [], []
    for it in rows:
        conf = it.get("confidence") or 0
        if conf < 0.6:
            continue
        z = zone(it.get("pctile_pe_fwd"), it.get("eps_growth_ntm"))
        rel, _ = zone_reliability(it.get("eps_growth_ntm"), it.get("growth_basis"), it.get("confidence"))
        v = (it.get("valuation_verdict") or "").upper()
        if z == "buy" and rel and not it.get("bubble_flag") and v in ("LEVNÁ", "FÉROVÁ"):
            cheap.append(it)
        elif v == "PŘEPÁLENÁ" or it.get("bubble_flag"):
            rich.append(it)
    cheap.sort(key=lambda it: -(zone_score(it.get("pctile_pe_fwd"), it.get("eps_growth_ntm")) or 0)
               - 5 * fund_buyers.get((it.get("ticker") or "").upper(), 0))
    rich.sort(key=lambda it: -(it.get("market_cap") or 0))
    return {"cheap": [enrich(i, "cheap") for i in cheap[:limit]],
            "expensive": [enrich(i, "expensive") for i in rich[:limit]]}
