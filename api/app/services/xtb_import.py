"""Import výpisu z XTB (xlsx „Account statement“: Closed Positions / Cash Operations / Open Positions).

Zdrojem transakcí je list Cash Operations — obsahuje celou historii po jednotlivých
operacích (každý fill nákupu/prodeje zvlášť, s ID operace a ID pozice):
  Stock purchase  „OPEN BUY NVDA.US 6/6.443 @ 138.50“   → buy  6 ks @ 138.50 (měna nástroje)
  Stock sell      „CLOSE BUY NVDA.US 3/3.2215 @ 136.02“ → sell 3 ks @ 136.02
  Dividend / Withholding tax                             → dividend (+ / −, v měně účtu)
  Free funds interest / … tax                            → interest / tax
  Deposit / Withdrawal                                   → deposit / withdrawal
Přeskakuje se: převody mezi vlastními podúčty (Transfer, Subaccount transfer) a CFD
(Close trade, Swap — patří do trading deníku, ne do investic).

List Open Positions slouží jako kontrola: počet kusů spočítaný z transakcí musí sedět
s tím, co XTB hlásí jako otevřené.
"""
from __future__ import annotations

import io
import re
from datetime import datetime

# Měna nástroje podle burzovního suffixu XTB. .UK obchoduje v GBP i USD → rozhodne kurz.
_CCY_BY_SUFFIX = {".US": "USD", ".DE": "EUR", ".NL": "EUR", ".FR": "EUR", ".IT": "EUR", ".ES": "EUR",
                  ".BE": "EUR", ".PT": "EUR", ".FI": "EUR", ".IE": "EUR", ".AT": "EUR",
                  ".CZ": "CZK", ".PL": "PLN", ".CH": "CHF", ".SW": "CHF", ".DK": "DKK", ".SE": "SEK", ".NO": "NOK"}
# Ticker v komentáři je jen v novějších výpisech („OPEN BUY 7/7.8865 @ 139.57“ starší).
_TRADE = re.compile(r"(OPEN|CLOSE)\s+(BUY|SELL)\s+(?:([A-Z][\w.]*)\s+)?([\d.]+)(?:/([\d.]+))?\s*@\s*([\d.]+)", re.I)

SKIP_TYPES = {"transfer": "převod mezi vlastními podúčty", "subaccount transfer": "převod mezi vlastními podúčty",
              "close trade": "CFD obchod", "swap": "swap CFD pozice"}
TYPE_MAP = {"stock purchase": "buy", "stock sell": "sell", "dividend": "dividend", "withholding tax": "dividend",
            "free funds interest": "interest", "free funds interest tax": "tax",
            "deposit": "deposit", "withdrawal": "withdrawal"}


def normalize_symbol(ticker: str) -> str:
    """NVDA.US → NVDA (jako ostatní brokeři a Valuation Radar); evropské tickery si suffix nechají."""
    t = (ticker or "").strip().upper()
    return t[:-3] if t.endswith(".US") else t


def instrument_currency(ticker: str, account_ccy: str, implied_rate: float | None) -> str:
    t = (ticker or "").upper()
    for suf, ccy in _CCY_BY_SUFFIX.items():
        if t.endswith(suf):
            return ccy
    if t.endswith(".UK") and implied_rate:
        if account_ccy == "CZK":
            return "GBP" if implied_rate >= 26.5 else ("GBX" if implied_rate < 1 else "USD")
        return "GBP"
    return account_ccy


def _sheet(wb, name: str) -> list[tuple]:
    for ws in wb.worksheets:
        if ws.title.strip().lower() == name.lower():
            return [r for r in ws.iter_rows(values_only=True)]
    return []


def _table(rows: list[tuple], first_col: str, must_have: str | None = None) -> list[dict]:
    """Řádky tabulky pod hlavičkou, jejíž první buňka je first_col (a obsahuje sloupec must_have —
    list Open Positions má nad pozicemi ještě souhrnnou tabulku se stejným prvním sloupcem)."""
    for i, r in enumerate(rows):
        if r and str(r[0] or "").strip() == first_col and (
                not must_have or must_have in [str(c or "").strip() for c in r]):
            hdr = [str(c or "").strip() for c in r]
            out = []
            for row in rows[i + 1:]:
                if not row or row[0] in (None, "") or str(row[0]).strip() in ("Total", "Profit/loss"):
                    continue
                out.append(dict(zip(hdr, row)))
            return out
    return []


def _dt(v) -> datetime | None:
    if isinstance(v, datetime):
        return v.replace(microsecond=0)
    try:
        return datetime.fromisoformat(str(v)).replace(microsecond=0)
    except (TypeError, ValueError):
        return None


def parse_xtb(content: bytes, account_ccy: str | None = None) -> dict:
    """xlsx → {"rows": [...transakce...], "skipped": {důvod: počet}, "open_positions": {symbol: kusy},
    "account": číslo účtu, "currency": měna účtu}. ValueError, když soubor není výpis z XTB."""
    import openpyxl  # jen pro import; ostatní endpointy ho nepotřebují
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:  # noqa: BLE001
        raise ValueError("Soubor nejde otevřít jako Excel (.xlsx).") from e
    cash_rows = _sheet(wb, "Cash Operations")
    ops = _table(cash_rows, "Type")
    if not ops:
        raise ValueError("Ve výpisu chybí list „Cash Operations“ — je to export z XTB (Historie účtu → Export)?")
    account = next((str(r[1]) for r in cash_rows if r and r[0] == "Account number"), None)
    ccy = (account_ccy or "CZK").upper()

    rows, skipped = [], {}
    for op in ops:
        typ = str(op.get("Type") or "").strip().lower()
        if typ in SKIP_TYPES:
            reason = SKIP_TYPES[typ]
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        tx_type = TYPE_MAP.get(typ)
        if not tx_type:
            skipped[f"neznámý typ „{op.get('Type')}“"] = skipped.get(f"neznámý typ „{op.get('Type')}“", 0) + 1
            continue
        amount = float(op.get("Amount") or 0)
        ticker = str(op.get("Ticker") or "").strip()
        product = str(op.get("Product") or "").strip()
        base = {"broker": "xtb", "external_id": str(op.get("ID") or "").strip() or None,
                "position_ref": str(op.get("Position ID") or "").strip() or None,
                "executed_at": _dt(op.get("Time")), "notes": f"XTB {product}".strip()}
        if tx_type in ("buy", "sell"):
            m = _TRADE.search(str(op.get("Comment") or ""))
            if not m:
                skipped["nečitelný komentář obchodu"] = skipped.get("nečitelný komentář obchodu", 0) + 1
                continue
            qty, price = float(m.group(4)), float(m.group(6))
            implied = abs(amount) / (qty * price) if qty and price else None
            rows.append({**base, "tx_type": tx_type, "symbol": normalize_symbol(ticker or m.group(3) or ""),
                         "name": op.get("Instrument") or None, "quantity": qty, "price": price,
                         "currency": instrument_currency(ticker or m.group(3) or "", ccy, implied),
                         "amount": round(abs(amount), 2), "amount_currency": ccy})
        else:
            note = {"Withholding tax": "srážková daň z dividendy"}.get(str(op.get("Type")).strip())
            rows.append({**base, "tx_type": tx_type, "symbol": normalize_symbol(ticker) or None,
                         "name": op.get("Instrument") or None, "currency": ccy,
                         "amount": round(amount if tx_type == "dividend" else abs(amount), 2),
                         "notes": f"{base['notes']} · {note}" if note else (f"{base['notes']} · {op.get('Comment')}"
                                                                           if tx_type in ("interest", "tax") else base["notes"])})

    open_pos: dict[str, float] = {}
    for p in _table(_sheet(wb, "Open Positions"), "Product", must_have="Ticker"):
        t, typ, vol = p.get("Ticker"), str(p.get("Type") or "").upper(), p.get("Volume")
        if t and typ == "BUY" and isinstance(vol, (int, float)):
            s = normalize_symbol(str(t))
            open_pos[s] = round(open_pos.get(s, 0) + float(vol), 6)
    return {"rows": rows, "skipped": skipped, "open_positions": open_pos, "account": account, "currency": ccy}


def holdings_check(rows: list[dict], open_pos: dict[str, float], tol: float = 1e-4) -> list[dict]:
    """Počet kusů z transakcí vs. Open Positions od XTB — rozdíly (prázdný seznam = sedí)."""
    calc: dict[str, float] = {}
    for r in rows:
        if r["tx_type"] in ("buy", "sell"):
            calc[r["symbol"]] = calc.get(r["symbol"], 0) + (r["quantity"] if r["tx_type"] == "buy" else -r["quantity"])
    out = []
    for s in sorted(set(calc) | set(open_pos)):
        a, b = round(calc.get(s, 0), 6), round(open_pos.get(s, 0), 6)
        if abs(a - b) > tol:
            out.append({"symbol": s, "z_transakci": a, "xtb_otevreno": b})
    return out
