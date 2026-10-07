"""TRADEZER investuje — AI paper-trading fond (řídí Spark).

Autoritativní stav = lokální SQLite (~/tradezer/fund.db). Algoritmus rozhoduje
z NAŠICH vlastních analýz (valuation + discovery + smart money + dark pool),
které čte z backendu (/api/fund/signals), a ke každému obchodu generuje DŮVOD.
Pak pushne zrcadlo na /api/fund/ingest pro frontend. Start kapitál 1 000 000 CZK.

Běh: TRADEZER_TOKEN=... py data/tradezer_fund.py --push   (--loop N minut)

Strategie (rules-based, vysvětlitelná):
  Konvikce = valuace (verdikt+skóre) + momentum (discovery) + insideři (smart money)
             + institucionální objem (dark pool).
  Nakupuje top konvikce (cílová váha dle konvikce, max 10 %, cash buffer 5 %).
  Max pár obchodů za běh, ať je log čitelný.

  FILOZOFIE (střednědobé příležitosti na 3+ let, ne splašené obchodování):
  • REŽIM TRHU (risk_regime.py) řídí nákupy: klid = běžně; stabilizace = po částech (½ váhy);
    napětí = jen nejsilnější příležitosti a po částech; panika = nenakupovat, počkat.
  • „Padající nůž": kandidát, který ještě padá (−8/−6/−4 % za 5 dní dle režimu), čeká na
    stabilizaci ceny — i když je levný.
  • NÁKUP jen u firem s ověřenou valuací (levná/férová) — žádné honění momenta bez fundamentu.
  • PRODEJE JEN VÝJIMEČNĚ (daň ze zisku, časový test 3 roky): žádné fixování zisku ani běžné
    ořezy; prodá se jen při zlomu teze (přepálená valuace A obrat signálů, nebo tvrdý obrat) a
    nikdy v panice. Zisková pozice držená <3 roky se kvůli dani neprodává, leda při tvrdém obratu.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, date

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # risk_regime.py leží vedle

UA = "Mozilla/5.0 TradezerFund/1.0"
BASE = os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "").strip()
DB_PATH = os.environ.get("FUND_DB", os.path.join(os.path.dirname(__file__), "fund.db"))
START_CAPITAL = 1_000_000.0
BASE_CCY = "CZK"

# Parametry strategie
MAX_WEIGHT = 0.10        # max 10 % equity na jednu pozici
CASH_BUFFER = 0.05       # drž aspoň 5 % hotovosti
BUY_TH = 22              # min konvikce pro nákup
SELL_TH = -8             # pod tuto konvikci prodat
MAX_BUYS = 4             # max nových/doplněných nákupů za běh
MIN_TRADE_CZK = 8000     # neobchoduj drobné

# ── Ochrana před splašeným obchodováním (horizont 3+ roky, daně) ─────────────
SELL_TAX_YEARS = 3                 # ČR: po 3 letech držení je zisk z prodeje osvobozen
HARD_SELL_TH = SELL_TH - 20        # tvrdý zlom teze (konvikce hluboko pod prahem)
OVERWEIGHT_TRIM = 2 * MAX_WEIGHT   # ořez nadváhy až při dvojnásobku povolené váhy

# Politika nákupů dle režimu trhu: kolik nákupů, jak velká část cílové váhy, minimální
# konvikce a práh „padajícího nože" (pokles za 5 dní, kdy kandidát počká na stabilizaci).
REGIME_POLICY = {
    "calm":       {"max_buys": MAX_BUYS, "size": 1.0, "min_score": BUY_TH,      "knife_pct": 8.0},
    "recovering": {"max_buys": 2,        "size": 0.5, "min_score": BUY_TH,      "knife_pct": 6.0},
    "tension":    {"max_buys": 1,        "size": 0.5, "min_score": BUY_TH + 12, "knife_pct": 4.0},
    "panic":      {"max_buys": 0,        "size": 0.0, "min_score": 10_000,      "knife_pct": 0.0},
}


def fundamentally_ok(d: dict) -> bool:
    """Horizont 3+ roky: kupujeme jen firmy s OVĚŘENOU valuací (levná / férová). Čistě momentová
    jména bez valuace (nebo drahá, napjatá, přepálená) fond nekupuje, ani když má vysoké skóre."""
    v = (d.get("verdict") or "").upper()
    return "LEVN" in v or "FÉR" in v or "FER" in v


def held_days(opened_at) -> int:
    try:
        return (date.today() - date.fromisoformat(str(opened_at)[:10])).days
    except (ValueError, TypeError):
        return 0


def sell_decision(conv: float, verdict: str | None, gain: float, days: int, state: str):
    """Kdy VÝJIMEČNĚ prodat celou pozici. Vrací (akce, důvod): akce = 'sell' | 'hold_tax' |
    'hold_regime' | None. Prodej jen při zlomu teze: přepálená valuace A obrat signálů
    (konvikce ≤ SELL_TH), nebo tvrdý obrat (konvikce ≤ HARD_SELL_TH). Nikdy v panice;
    v napětí jen tvrdý obrat; zisková pozice <3 roky se neprodává (daň) kromě tvrdého obratu."""
    v = (verdict or "").upper()
    overvalued = "PŘEPÁL" in v or "PREPAL" in v
    hard = conv <= HARD_SELL_TH
    thesis = overvalued and conv <= SELL_TH
    if not (hard or thesis):
        return None, ""
    if state == "panic":
        return "hold_regime", "režim PANIKA — ve stresu neprodáváme"
    if state == "tension" and not hard:
        return "hold_regime", "režim NAPĚTÍ — prodej kvůli valuaci počká na klidnější trh"
    if gain > 0 and days < SELL_TAX_YEARS * 365 and not hard:
        return "hold_tax", f"zisk {gain * 100:+.0f} %, držíme {days} dní (<3 roky) — prodej by byl zdaněný"
    return "sell", ("tvrdý obrat signálů" if hard else "přepálená valuace + obrat signálů")


def falling_knife(closes: list[float], thr_pct: float):
    """(padá_ještě?, výnos 5 dní v %). Padá = −thr % za 5 obchodních dní, nebo nové 5denní
    minimum při poklesu aspoň poloviny prahu. Levná, ale ještě padající akcie počká na stabilizaci."""
    if thr_pct <= 0 or len(closes) < 7:
        return False, None
    ret5 = (closes[-1] / closes[-6] - 1) * 100
    new_low = closes[-1] <= min(closes[-6:-1])
    return (ret5 <= -thr_pct) or (new_low and ret5 <= -thr_pct / 2), ret5


def daily_closes(symbol: str) -> list[float]:
    try:
        res = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{_yahoo_sym(symbol)}?range=1mo&interval=1d")["chart"]["result"][0]
        return [float(c) for c in (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or [] if c is not None]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TypeError, ValueError, TimeoutError):
        return []


# ── Yahoo ceny + FX ─────────────────────────────────────────────────────────
_YH_ALIAS = {"KWBE": "KWBE.DE"}
_YH_SUFFIX = {".NV": ".AS", ".NL": ".AS", ".UK": ".L", ".GB": ".L"}


def _yahoo_sym(s: str) -> str:
    s = s.upper()
    if s in _YH_ALIAS:
        return _YH_ALIAS[s]
    if s.endswith(".US"):
        return s[:-3]
    for suf, rep in _YH_SUFFIX.items():
        if s.endswith(suf):
            return s[:-len(suf)] + rep
    return s


def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def yahoo_price(symbol: str):
    try:
        res = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{_yahoo_sym(symbol)}?range=5d&interval=1d")["chart"]["result"][0]
        meta = res["meta"]
        p = meta.get("regularMarketPrice")
        return (float(p), meta.get("currency") or "USD") if p is not None else (None, None)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TypeError, ValueError, TimeoutError):
        return None, None


def gspc_history() -> list[tuple[str, float]]:
    """(date, close) S&P 500 (^GSPC) za 2 roky — benchmark fondu. Seřazené ASC."""
    try:
        res = _get("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=2y&interval=1d")["chart"]["result"][0]
        ts = res.get("timestamp") or []
        closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        return [(time.strftime("%Y-%m-%d", time.gmtime(t)), float(c)) for t, c in zip(ts, closes) if c is not None]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TypeError, ValueError, TimeoutError):
        return []


def _close_le(arr: list[tuple[str, float]], d: str):
    """Poslední close ≤ datum (arr seřazené ASC)."""
    import bisect
    i = bisect.bisect_right([a[0] for a in arr], d)
    return arr[i - 1][1] if i > 0 else (arr[0][1] if arr else None)


# ── LLM narativ (gpt-oss na Sparku přes gateway; bez LLM_BASE_URL → rules-based) ──
def llm_available() -> bool:
    return bool(os.environ.get("LLM_BASE_URL", "").strip())


def llm_chat(system: str, user: str, max_tokens: int = 500) -> str | None:
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    if not base:
        return None
    body = json.dumps({
        "model": os.environ.get("LLM_MODEL", "heavy"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens, "temperature": 0.5,
    }).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + os.environ.get("LLM_API_KEY", "")})
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            txt = json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()
        # ořízni případné <think>…</think> nebo úvahové bloky
        if "</think>" in txt:
            txt = txt.split("</think>")[-1].strip()
        return txt or None
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TypeError, ValueError, TimeoutError) as e:
        print(f"  LLM fail: {e}")
        return None


def _parse_numbered(text: str, n: int) -> dict:
    """Rozparsuje očíslované řádky '1) …' → {index: text}."""
    import re
    out = {}
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)[).\]]\s*(.+)", line)
        if m:
            i = int(m.group(1)) - 1
            if 0 <= i < n:
                out[i] = m.group(2).strip()
    return out


# ── Backend I/O ──────────────────────────────────────────────────────────────
def fetch_signals():
    try:
        return _get(f"{BASE}/api/fund/signals", {"User-Agent": UA, "X-Internal-Token": TOKEN}, 30)
    except Exception as e:  # noqa: BLE001
        print(f"  signals fail: {e}")
        return {}


def push_mirror(state, positions, trades, snapshots):
    body = json.dumps({"state": state, "positions": positions,
                       "trades": trades, "snapshots": snapshots}).encode()
    req = urllib.request.Request(f"{BASE}/api/fund/ingest", data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "X-Internal-Token": TOKEN, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            print(f"  push OK: {r.read().decode()[:120]}")
    except urllib.error.HTTPError as e:
        print(f"  push HTTP {e.code}: {e.read().decode()[:160]}")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  push fail {e}")


# ── Lokální DB (stav fondu — autoritativní na Sparku) ────────────────────────
def db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY, cash REAL, start_capital REAL);
    CREATE TABLE IF NOT EXISTS positions(symbol TEXT PRIMARY KEY, name TEXT, qty REAL, avg_cost REAL,
      currency TEXT, opened_at TEXT, conviction REAL);
    CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, action TEXT, symbol TEXT,
      name TEXT, qty REAL, price REAL, currency TEXT, value_czk REAL, realized_czk REAL, conviction REAL, reason TEXT);
    CREATE TABLE IF NOT EXISTS snapshots(date TEXT PRIMARY KEY, equity REAL, cash REAL, invested REAL);
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    row = con.execute("SELECT cash FROM state WHERE id=1").fetchone()
    if row is None:
        con.execute("INSERT INTO state(id,cash,start_capital) VALUES(1,?,?)", (START_CAPITAL, START_CAPITAL))
        con.commit()
    return con


# ── Skórování konvikce z našich analýz ───────────────────────────────────────
def _verdict_pts(v: str | None) -> tuple[float, str]:
    v = (v or "").upper()
    if "LEVN" in v or "VHODN" in v:
        return 25, "akcie je podle fundamentů levná a vhodná k držbě — obchoduje se pod svou férovou hodnotou"
    if "FÉR" in v or "FER" in v:
        return 10, "valuace je férová (cena odpovídá fundamentům)"
    if "NAPJAT" in v:
        return -10, "valuace je napjatá (spíš dráž)"
    if "PŘEPÁL" in v or "PREPAL" in v:
        return -28, "valuace je přepálená (akcie je drahá vůči fundamentům)"
    return 0, ""


def score_candidates(sig: dict) -> dict:
    """Vrátí {ticker: {score, name, currency?, reasons[], verdict}}."""
    C: dict[str, dict] = {}

    def ensure(tk, name=None):
        d = C.setdefault(tk, {"score": 0.0, "name": name, "reasons": [], "verdict": None})
        if name and not d["name"]:
            d["name"] = name
        return d

    for v in sig.get("valuation", []):
        tk = (v.get("ticker") or "").upper()
        if not tk:
            continue
        d = ensure(tk, v.get("name"))
        d["verdict"] = v.get("verdict")
        pts, why = _verdict_pts(v.get("verdict"))
        d["score"] += pts
        comp = v.get("composite")
        if comp is not None:
            d["score"] += (comp - 50) / 3.0  # ±~16
            d["composite"] = comp
        if why:
            d["reasons"].append(why + (f" (fundamentální skóre {comp:.0f}/100)" if comp is not None else ""))
        hz = v.get("horizon")
        if hz:
            d["reasons"].append(f"dlouhodobý výhled: {str(hz).lower()}")

    for it in sig.get("discovery", []):
        tk = (it.get("ticker") or "").upper()
        if not tk:
            continue
        d = ensure(tk)
        sc = it.get("score") or 0
        d["score"] += min(sc / 6.0, 16)
        r20 = it.get("ret_20d")
        if r20 and r20 > 0:
            d["score"] += min(r20 / 3.0, 10)
            d["reasons"].append(f"cena má vzestupné momentum (+{r20:.0f} % za 20 dní)")
        if (it.get("rel_vol") or 0) >= 1.8:
            d["score"] += 4
            d["reasons"].append("zvýšený objem obchodování (zájem trhu)")
        if (it.get("news_7d") or 0) >= 2:
            d["score"] += 3
            d["reasons"].append(f"aktivní newsflow ({it.get('news_7d')} zpráv za týden)")
        dte = it.get("days_to_earnings")
        if dte is not None and 0 <= dte <= 10:
            d["reasons"].append(f"blíží se výsledky (earnings za {dte} dní)")

    buys = {(b.get("ticker") or "").upper() for b in sig.get("smart_money_top_buys", [])}
    for tk in buys:
        if tk:
            d = ensure(tk); d["score"] += 15
            d["reasons"].append("insideři (vedení firmy) akcie sami nakupují — věří jí")

    dp = {(x.get("symbol") or "").upper() for x in sig.get("dark_pool", [])[:20]}
    for tk in dp:
        if tk in C:
            C[tk]["score"] += 4
            C[tk]["reasons"].append("silný objem v dark pools = zájem velkých institucí")

    return C


# ── Rozhodovací engine ───────────────────────────────────────────────────────
def run(do_push: bool, dry: bool):
    if not TOKEN:
        sys.exit("Chybí TRADEZER_TOKEN.")
    con = db()
    cash, start_cap = con.execute("SELECT cash,start_capital FROM state WHERE id=1").fetchone()
    positions = {r[0]: {"name": r[1], "qty": r[2], "avg_cost": r[3], "currency": r[4],
                        "opened_at": r[5], "conviction": r[6]}
                 for r in con.execute("SELECT symbol,name,qty,avg_cost,currency,opened_at,conviction FROM positions")}

    gspc = gspc_history()  # benchmark fetch brzy (než Yahoo throttlne po cenách)
    sig = fetch_signals()
    C = score_candidates(sig)
    print(f"stav: cash {cash:.0f} CZK, {len(positions)} pozic | kandidátů {len(C)} | ^GSPC barů {len(gspc)}")

    # Režim trhu (klid / stabilizace / napětí / panika) — řídí nákupy a brání prodejům ve stresu
    try:
        import risk_regime
        rg = risk_regime.get_regime()
    except Exception as e:  # noqa: BLE001 — bez režimu jedeme jako klid, ale nahlas
        print(f"  režim trhu nedostupný ({e}) — předpokládám klid")
        rg = None
    state = (rg or {}).get("state") or "calm"
    pol = REGIME_POLICY.get(state, REGIME_POLICY["calm"])
    ctx = {"state": state, "label": (rg or {}).get("label", "Klid"), "reasons": (rg or {}).get("reasons", []),
           "waiting": [], "watch": [], "tax_holds": [], "sell_deferred": [], "known": rg is not None}
    print(f"režim trhu: {ctx['label']} → max nákupů {pol['max_buys']}, velikost {pol['size']:.0%}, "
          f"min. konvikce {pol['min_score']}")

    # Ceny + FX pro všechny relevantní tickery
    need = set(positions) | {tk for tk, d in C.items() if d["score"] >= BUY_TH}
    prices, ccy = {}, {}
    for tk in sorted(need):
        p, cu = yahoo_price(tk)
        if p is not None:
            prices[tk] = p; ccy[tk] = cu
        time.sleep(0.25)
    fx = {}
    for cu in set(ccy.values()) | {positions[p]["currency"] for p in positions}:
        if cu and cu != BASE_CCY:
            fp, _ = yahoo_price(f"{cu}{BASE_CCY}=X")
            if fp:
                fx[cu] = fp
            time.sleep(0.25)

    def to_czk(amount, cu):
        return amount * (1.0 if cu == BASE_CCY else fx.get(cu, 0))

    # aktuální equity
    def equity_now():
        inv = sum(positions[s]["qty"] * prices.get(s, positions[s]["avg_cost"]) *
                  (1.0 if positions[s]["currency"] == BASE_CCY else fx.get(positions[s]["currency"], 0))
                  for s in positions)
        return cash + inv, inv

    trades_this_run = []
    now = datetime.utcnow().isoformat(timespec="seconds")
    today = date.today().isoformat()

    def log_trade(action, sym, name, qty, price, cu, conv, reason, realized=None):
        v_czk = to_czk(qty * price, cu)
        con.execute("INSERT INTO trades(ts,action,symbol,name,qty,price,currency,value_czk,realized_czk,conviction,reason)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (now, action, sym, name, qty, price, cu, v_czk, realized, conv, reason))
        trades_this_run.append((action, sym, qty, reason))
        print(f"  {action.upper()} {qty:.2f} {sym} @ {price:.2f} {cu} — {reason}")

    equity, _ = equity_now()

    # ── PRODEJE / OŘEZY ──
    for sym in list(positions):
        pos = positions[sym]
        pr = prices.get(sym)
        if pr is None:
            continue
        cu = pos["currency"]
        conv = C.get(sym, {}).get("score", 0)
        verdict = C.get(sym, {}).get("verdict")
        gain = (pr - pos["avg_cost"]) / pos["avg_cost"] if pos["avg_cost"] else 0
        val_czk = to_czk(pos["qty"] * pr, cu)
        weight = val_czk / equity if equity else 0
        realized = to_czk((pr - pos["avg_cost"]) * pos["qty"], cu)

        # PRODEJ JEN VÝJIMEČNĚ (daň ze zisku, horizont 3+ roky): zlom teze, nikdy v panice
        days = held_days(pos.get("opened_at"))
        action, why = sell_decision(conv, verdict, gain, days, state)
        if action == "sell":
            reason = (f"Výjimečný prodej celé pozice — {why}: konvikce klesla na {conv:.0f}/100"
                      f"{f', valuace {verdict}' if verdict else ''}. Realizováno {realized:+.0f} Kč ({gain*100:+.0f} %). "
                      f"Fond jinak neprodává (nechceme platit daň ze zisku), tady teze pro držení přestala platit.")
            log_trade("sell", sym, pos["name"], pos["qty"], pr, cu, conv, reason, realized)
            cash += val_czk
            del positions[sym]
            continue
        if action == "hold_tax":
            ctx["tax_holds"].append(f"{sym} ({why})")
            continue
        if action == "hold_regime":
            ctx["sell_deferred"].append(f"{sym} ({why})")
            continue
        # ořez nadváhy jen EXTRÉMNÍ (≥ 2× povolená váha) a ne při zdaněném zisku
        if weight > OVERWEIGHT_TRIM and not (gain > 0 and days < SELL_TAX_YEARS * 365):
            target_czk = MAX_WEIGHT * equity
            qsell = round((val_czk - target_czk) / (pr * (fx.get(cu, 1) if cu != BASE_CCY else 1)), 4)
            if qsell > 0 and to_czk(qsell * pr, cu) >= MIN_TRADE_CZK:
                reason = (f"Výjimečný ořez: váha vzrostla na {weight*100:.0f} % (limit {MAX_WEIGHT*100:.0f} %), "
                          f"snižuji k cílovým {MAX_WEIGHT*100:.0f} %. Pozice je ve ztrátě nebo starší 3 let, takže se nezdaní.")
                log_trade("trim", sym, pos["name"], qsell, pr, cu, conv, reason)
                cash += to_czk(qsell * pr, cu); pos["qty"] -= qsell
        elif weight > OVERWEIGHT_TRIM:
            ctx["tax_holds"].append(f"{sym} (nadváha {weight*100:.0f} %, ale zisk by se zdanil)")

    # ── NÁKUPY ──
    equity, _ = equity_now()
    all_cand = sorted(([tk, d] for tk, d in C.items()
                       if d["score"] >= BUY_TH and tk in prices and fundamentally_ok(d)),
                      key=lambda x: x[1]["score"], reverse=True)
    cand = [c for c in all_cand if c[1]["score"] >= pol["min_score"]]
    buys_done = 0
    bought = set()
    for tk, d in cand:
        if buys_done >= pol["max_buys"]:
            break
        if cash <= equity * CASH_BUFFER:
            break
        pr = prices[tk]; cu = ccy.get(tk, "USD")
        # „padající nůž": levná, ale ještě padající akcie počká na stabilizaci ceny
        knife, ret5 = falling_knife(daily_closes(tk), pol["knife_pct"])
        time.sleep(0.25)
        if knife:
            ctx["waiting"].append(f"{tk} ({ret5:+.0f} % za 5 dní)")
            print(f"  ČEKÁ {tk}: konvikce {d['score']:.0f}, ale cena ještě padá ({ret5:+.1f} % za 5 dní)")
            continue
        # cílová váha dle konvikce (lineárně 22→60 na 3→10 %), v režimu napětí/stabilizace jen její část
        tgt_w = min(MAX_WEIGHT, 0.03 + (d["score"] - BUY_TH) / 38.0 * (MAX_WEIGHT - 0.03))
        tgt_czk = tgt_w * equity * pol["size"]
        cur_czk = to_czk(positions.get(tk, {"qty": 0, "currency": cu})["qty"] * pr, cu) if tk in positions else 0
        buy_czk = min(tgt_czk - cur_czk, cash - equity * CASH_BUFFER)
        if buy_czk < MIN_TRADE_CZK:
            continue
        unit_czk = to_czk(pr, cu)
        if unit_czk <= 0:
            continue
        qty = round(buy_czk / unit_czk, 4)
        if qty <= 0:
            continue
        frags = d["reasons"] or ["kompozitní skóre našich signálů je nadprůměrné"]
        body = ". ".join(s[0].upper() + s[1:] for s in frags)
        reason = (f"{body}. Celková konvikce {d['score']:.0f}/100 spojuje všechny tyto signály "
                  f"(valuace, momentum, insideři, dark pool) — čím vyšší, tím silnější přesvědčení; "
                  f"podle ní fond nastavil cílovou váhu {tgt_w*100:.0f} % portfolia (~{buy_czk:.0f} Kč).")
        if state != "calm":
            reason += (f" Režim trhu je {ctx['label'].upper()}, proto fond vstupuje jen po částech "
                       f"({pol['size']*100:.0f} % cílové váhy) a zbytek doplní, až se situace uklidní.")
        log_trade("buy", tk, d["name"], qty, pr, cu, d["score"], reason)
        bought.add(tk)
        cost = to_czk(qty * pr, cu); cash -= cost
        if tk in positions:
            p0 = positions[tk]
            tot = p0["qty"] + qty
            p0["avg_cost"] = (p0["avg_cost"] * p0["qty"] + pr * qty) / tot if tot else pr
            p0["qty"] = tot; p0["conviction"] = d["score"]
        else:
            positions[tk] = {"name": d["name"], "qty": qty, "avg_cost": pr, "currency": cu,
                             "opened_at": today, "conviction": d["score"]}
        buys_done += 1

    # Silné příležitosti, které fond kvůli režimu nekoupil — sleduje je (do poznámky)
    if state != "calm":
        ctx["watch"] = [f"{tk} (konvikce {d['score']:.0f})" for tk, d in all_cand
                        if tk not in bought and not any(w.startswith(tk + " ") for w in ctx["waiting"])][:5]

    # ── Ulož stav + snapshot ──
    con.execute("DELETE FROM positions")
    for sym, p in positions.items():
        if p["qty"] > 1e-9:
            con.execute("INSERT INTO positions(symbol,name,qty,avg_cost,currency,opened_at,conviction) VALUES(?,?,?,?,?,?,?)",
                        (sym, p["name"], p["qty"], p["avg_cost"], p["currency"], p.get("opened_at"), p.get("conviction")))
    equity, invested = equity_now()
    con.execute("UPDATE state SET cash=? WHERE id=1", (cash,))
    con.execute("INSERT OR REPLACE INTO snapshots(date,equity,cash,invested) VALUES(?,?,?,?)",
                (today, equity, cash, invested))
    con.commit()

    pnl = equity - start_cap
    print(f"equity {equity:.0f} CZK (P/L {pnl:+.0f} / {pnl/start_cap*100:+.1f} %), cash {cash:.0f}, {len(positions)} pozic, {len(trades_this_run)} obchodů")

    if dry:
        con.close(); return
    if not do_push:
        con.close(); return

    # ── Zrcadlo do Neonu ──
    note = _build_note(trades_this_run, equity, start_cap, ctx)
    # LLM narativ (gpt-oss na Sparku) — ROZVEDE každý důvod do bohaté podoby (per-trade,
    # spolehlivější než dávka) + 2větné shrnutí dne. Fallback = bohatý rules-based důvod.
    if trades_this_run and llm_available():
        act_cs = {"buy": "koupil", "sell": "prodal celou pozici", "trim": "odebral část pozice"}
        rows = con.execute("SELECT id,action,symbol,name,reason FROM trades WHERE ts=? ORDER BY id", (now,)).fetchall()
        for rid, action, sym, name, base_reason in rows:
            out = llm_chat(
                "Jsi zkušený portfolio manažer AI fondu TRADEZER. Píšeš česky, čtivě a sebevědomě pro drobné "
                "investory, aby rozhodnutí fondu pochopil i laik. Bez úvah a bez uvozovek, jen 2–3 věty finálního textu.",
                f"Fond {act_cs.get(action, action)} akcii {name or sym} ({sym}). Rozveď následující fakta do 2–3 "
                f"poutavých vět — zachovej všechna čísla, vysvětli signály lidsky a co pro investora znamenají. "
                f"Fakta: {base_reason}", max_tokens=600)
            # Použij LLM jen když vrátil DOKONČENÝ text (končí tečkou/…) — jinak nech
            # bohatý rules-based důvod (gpt-oss občas utne výstup kvůli reasoningu).
            if out and len(out) > 40 and out.rstrip()[-1] in ".!?%)":
                con.execute("UPDATE trades SET reason=? WHERE id=?", (out, rid))
        con.commit()
        listing = "; ".join(f"{a} {s}" for a, s, q, r in trades_this_run)
        nt = llm_chat(
            "Jsi portfolio manažer AI fondu TRADEZER, píšeš česky pro zákazníky. Bez úvah, jen 2 věty.",
            f"Shrň poslední tah fondu do 2 sebevědomých vět (nepoužívej slovo „dnes“, text se čte i další dny). "
            f"Hodnota {equity:.0f} CZK ({(equity-start_cap)/start_cap*100:+.1f} %). Obchody tahu: {listing}.", max_tokens=400)
        if nt and nt.rstrip()[-1:] in (".", "!", "?", "%", ")"):
            note = (nt.rstrip() + " " + _ctx_text(ctx)).strip()
    # poznámka posledního tahu si pamatujeme — přecenění ji pak znovu pushuje (nezestárne na „dnes")
    _meta_set(con, "note", note)
    _meta_set(con, "note_date", today)
    _meta_set(con, "last_decision", now)
    con.commit()
    push_mirror(*_mirror(con, positions, prices, to_czk, cash, equity, start_cap, note, today, now, gspc))
    con.close()


def _meta_get(con, key, default=None):
    r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def _meta_set(con, key, value):
    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value))


def _cost_basis_czk(con) -> dict[str, float]:
    """Zbývající pořizovací cena pozic v Kč z historie obchodů (kurz platný v den obchodu,
    metoda průměrné ceny: prodej/ořez ubere poměrnou část nákladu)."""
    qty: dict[str, float] = {}
    cost: dict[str, float] = {}
    for action, sym, q, v in con.execute("SELECT action,symbol,qty,value_czk FROM trades ORDER BY id"):
        q, v = q or 0.0, v or 0.0
        if action == "buy":
            qty[sym] = qty.get(sym, 0.0) + q
            cost[sym] = cost.get(sym, 0.0) + v
        elif qty.get(sym, 0.0) > 1e-12:  # sell / trim
            frac = min(1.0, q / qty[sym])
            cost[sym] *= (1 - frac)
            qty[sym] -= q
    return {s: c for s, c in cost.items() if qty.get(s, 0.0) > 1e-9}


def _mirror(con, positions, prices, to_czk, cash, equity, start_cap, note, note_date, now, gspc):
    """Sestaví payload pro /api/fund/ingest. Poznámka nese datum tahu jako prefix
    `YYYY-MM-DD|text` (frontend ho rozparsuje → „Poslední tah fondu (6. 10.)")."""
    cost_czk = _cost_basis_czk(con)
    pos_out = []
    for sym, p in positions.items():
        if p["qty"] <= 1e-9:
            continue
        pr = prices.get(sym, p["avg_cost"]); cu = p["currency"]
        v = to_czk(p["qty"] * pr, cu)
        # P/L v Kč = hodnota − skutečně zaplacené koruny (kurz v době nákupu) → součet pozic
        # sedí s celkovým výnosem fondu (zahrnuje i pohyb kurzu USD/CZK). Fallback: cenový rozdíl.
        unreal = v - cost_czk[sym] if sym in cost_czk else to_czk((pr - p["avg_cost"]) * p["qty"], cu)
        pos_out.append({"symbol": sym, "name": p["name"], "quantity": round(p["qty"], 4),
                        "avg_cost": round(p["avg_cost"], 4), "currency": cu, "last_price": pr,
                        "value_czk": round(v), "unrealized_czk": round(unreal),
                        "weight_pct": round(v / equity * 100, 2) if equity else 0,
                        "opened_at": p.get("opened_at"), "conviction": round(p.get("conviction") or 0, 1)})
    trades_out = [dict(zip(["ts", "action", "symbol", "name", "qty", "price", "currency", "value_czk", "realized_czk", "conviction", "reason"], r))
                  for r in con.execute("SELECT ts,action,symbol,name,qty,price,currency,value_czk,realized_czk,conviction,reason FROM trades ORDER BY id DESC LIMIT 600")]
    # přejmenuj qty→quantity pro backend
    for t in trades_out:
        t["quantity"] = t.pop("qty")
    # benchmark: 1 mil. vložený do S&P 500 v den startu fondu (index return)
    snap_rows = con.execute("SELECT date,equity,cash,invested FROM snapshots ORDER BY date").fetchall()
    gstart = _close_le(gspc, snap_rows[0][0]) if (gspc and snap_rows) else None
    snaps_out = []
    for d, eq, ca, inv in snap_rows:
        gd = _close_le(gspc, d)
        bench = round(start_cap * gd / gstart) if (gstart and gd) else None
        snaps_out.append({"date": d, "equity": eq, "cash": ca, "invested": inv, "benchmark": bench})
    state_out = {"start_capital": start_cap, "cash": round(cash), "equity": round(equity),
                 "base": BASE_CCY, "as_of": now, "note": f"{note_date}|{note}" if note else note}
    return state_out, pos_out, trades_out, snaps_out


def mark(do_push: bool):
    """Lehké PŘECENĚNÍ bez obchodování: nové ceny+FX držených pozic → equity/P&L, snapshot
    dnešního dne (přepíše) a push zrcadla s uloženou poznámkou posledního tahu.
    Cena = pár Yahoo dotazů (jen držené tituly), žádné LLM ani signály."""
    if not TOKEN:
        sys.exit("Chybí TRADEZER_TOKEN.")
    con = db()
    cash, start_cap = con.execute("SELECT cash,start_capital FROM state WHERE id=1").fetchone()
    positions = {r[0]: {"name": r[1], "qty": r[2], "avg_cost": r[3], "currency": r[4],
                        "opened_at": r[5], "conviction": r[6]}
                 for r in con.execute("SELECT symbol,name,qty,avg_cost,currency,opened_at,conviction FROM positions")}
    if not positions:
        print("přecenění: žádné pozice"); con.close(); return
    prices, fx = {}, {}
    for tk in sorted(positions):
        p, _ = yahoo_price(tk)
        if p is not None:
            prices[tk] = p
        time.sleep(0.25)
    for cu in {p["currency"] for p in positions.values()}:
        if cu and cu != BASE_CCY:
            fp, _ = yahoo_price(f"{cu}{BASE_CCY}=X")
            if fp:
                fx[cu] = fp
            time.sleep(0.25)
    missing = [s for s in positions if s not in prices]
    if missing or any(positions[s]["currency"] not in fx and positions[s]["currency"] != BASE_CCY for s in positions):
        # neúplná data by zkreslila equity (chybějící cena = nákupní cena, chybějící FX = 0) → raději nic
        print(f"přecenění přeskočeno: chybí ceny {missing} / FX {sorted(fx)}"); con.close(); return

    def to_czk(amount, cu):
        return amount * (1.0 if cu == BASE_CCY else fx.get(cu, 0))
    inv = sum(to_czk(p["qty"] * prices[s], p["currency"]) for s, p in positions.items())
    equity = cash + inv
    now = datetime.utcnow().isoformat(timespec="seconds")
    today = date.today().isoformat()
    con.execute("INSERT OR REPLACE INTO snapshots(date,equity,cash,invested) VALUES(?,?,?,?)",
                (today, equity, cash, inv))
    con.commit()
    pnl = equity - start_cap
    print(f"přecenění: equity {equity:.0f} CZK (P/L {pnl:+.0f} / {pnl/start_cap*100:+.2f} %), cash {cash:.0f}")
    if do_push:
        note, note_date = _meta_get(con, "note"), _meta_get(con, "note_date")
        if not note:
            note, note_date = _last_move(con, equity, start_cap)
        gspc = gspc_history()
        push_mirror(*_mirror(con, positions, prices, to_czk, cash, equity, start_cap, note,
                             note_date or today, now, gspc))
    con.close()


def _us_market_hours(now_utc: datetime) -> bool:
    """Po–pá 13:30–21:30 UTC (US cash session + chvíle po zavíračce pro závěrečnou cenu)."""
    if now_utc.weekday() >= 5:
        return False
    m = now_utc.hour * 60 + now_utc.minute
    return 13 * 60 + 30 <= m <= 21 * 60 + 30


_REGIME_LINE = {
    "panic": "Fond nenakupuje a čeká na stabilizaci trhu; neprodává (nechceme platit daň ze zisku).",
    "tension": "Nakupuje jen nejsilnější příležitosti a po částech.",
    "recovering": "Po šoku se trh stabilizuje, fond nakupuje opatrně po částech.",
}


def _ctx_text(ctx: dict | None) -> str:
    """Věta o režimu trhu a o tom, na co fond čeká / co kvůli dani nedělá."""
    if not ctx:
        return ""
    out = []
    if ctx.get("state") and ctx["state"] != "calm":
        why = "; ".join((ctx.get("reasons") or [])[:2])
        out.append(f"Režim trhu: {ctx.get('label', '')}{f' ({why})' if why else ''}. {_REGIME_LINE.get(ctx['state'], '')}")
    if not ctx.get("known", True):
        out.append("Režim trhu se nepodařilo zjistit, fond postupoval opatrně jako při klidu.")
    if ctx.get("waiting"):
        out.append("Čeká na stabilizaci ceny: " + ", ".join(ctx["waiting"]) + ".")
    if ctx.get("watch"):
        out.append("Sleduje příležitosti: " + ", ".join(ctx["watch"]) + ".")
    if ctx.get("sell_deferred"):
        out.append("Prodej odložen: " + ", ".join(ctx["sell_deferred"]) + ".")
    if ctx.get("tax_holds"):
        out.append("Neprodává kvůli dani: " + ", ".join(ctx["tax_holds"]) + ".")
    return " ".join(out)


def _build_note(trades, equity, start_cap, ctx=None) -> str:
    # bez slova „dnes" — poznámka se zobrazuje i další dny s datem tahu (viz _mirror)
    pnl = equity - start_cap
    eq = f"{equity:,.0f}".replace(",", " ")  # mezera jako oddělovač tisíců (jen v čísle, ne v seznamu tickerů)
    extra = _ctx_text(ctx)
    if not trades:
        return (f"Bez obchodu — držím stávající pozice. {extra} Hodnota {eq} CZK ({pnl/start_cap*100:+.2f} %).").replace("  ", " ")
    acts = {}
    for a, s, q, r in trades:
        acts.setdefault(a, []).append(s)
    parts = []
    if acts.get("buy"):
        parts.append("nakoupil " + ", ".join(acts["buy"]))
    if acts.get("trim"):
        parts.append("ořezal " + ", ".join(acts["trim"]))
    if acts.get("sell"):
        parts.append("prodal " + ", ".join(acts["sell"]))
    return ("Fond " + "; ".join(parts) + f". {extra} Hodnota po tahu {eq} CZK ({pnl/start_cap*100:+.2f} %).").replace("  ", " ")


def _last_move(con, equity, start_cap):
    """(poznámka, datum) posledního tahu odvozené z DB — pro starou DB bez `meta`."""
    r = con.execute("SELECT MAX(ts) FROM trades").fetchone()[0]
    if not r:
        return _build_note([], equity, start_cap), date.today().isoformat()
    rows = con.execute("SELECT action,symbol,qty,reason FROM trades WHERE ts=? ORDER BY id", (r,)).fetchall()
    return _build_note(rows, equity, start_cap), r[:10]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--dry", action="store_true", help="jen spočítej, neukládej/nepushuj")
    ap.add_argument("--loop", type=int, default=0, help="opakuj každých N minut (Spark: 1440 = denně)")
    ap.add_argument("--mark-every", type=int, default=0,
                    help="s --loop: mezi rozhodovacími běhy přeceňuj pozice každých N minut "
                         "(jen v obchodní době USA) a pushuj nové P/L")
    ap.add_argument("--mark-now", action="store_true", help="jen jednorázové přecenění + push (bez obchodů)")
    args = ap.parse_args()
    if args.mark_now:
        mark(args.push)
        return
    if args.mark_every > 0 and args.loop > 0:
        first = True
        while True:
            now = datetime.utcnow()
            con = db()
            last = _meta_get(con, "last_decision") or con.execute("SELECT MAX(ts) FROM trades").fetchone()[0]
            con.close()
            due = last is None or (now - datetime.fromisoformat(last)).total_seconds() >= args.loop * 60
            try:
                if due:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M')}] TRADEZER investuje (rozhodovací běh) -> {BASE}")
                    run(args.push, args.dry)
                elif first or _us_market_hours(now):
                    print(f"[{time.strftime('%Y-%m-%d %H:%M')}] přecenění")
                    mark(args.push)
            except Exception as e:  # noqa: BLE001 — jeden špatný běh nesmí shodit službu
                print(f"  chyba běhu: {e}")
            first = False
            time.sleep(args.mark_every * 60)
    while True:
        print(f"[{time.strftime('%Y-%m-%d %H:%M')}] TRADEZER investuje -> {BASE} (db {DB_PATH})")
        run(args.push, args.dry)
        if args.loop <= 0:
            break
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
