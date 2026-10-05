"""TRADEZER investuje — AI paper-trading fond (řídí Spark).

Autoritativní stav = lokální SQLite (~/tradezer/fund.db). Algoritmus rozhoduje
z NAŠICH vlastních analýz (valuation + discovery + smart money + dark pool),
které čte z backendu (/api/fund/signals), a ke každému obchodu generuje DŮVOD.
Pak pushne zrcadlo na /api/fund/ingest pro frontend. Start kapitál 1 000 000 CZK.

Běh: TRADEZER_TOKEN=... py data/tradezer_fund.py --push   (--loop N minut)

Strategie (rules-based, vysvětlitelná):
  Konvikce = valuace (verdikt+skóre) + momentum (discovery) + insideři (smart money)
             + institucionální objem (dark pool).
  Nakupuje top konvikce (cílová váha dle konvikce, max 10 %, cash buffer 5 %),
  prodává při PŘEPÁLENÉ valuaci / obratu, fixuje část zisku u napjaté valuace,
  ořezává nadváhu. Max pár obchodů za běh, ať je log čitelný.
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
TRIM_GAIN = 0.40         # zisk nad 40 % + napjatá valuace → fixovat část
MAX_BUYS = 4             # max nových/doplněných nákupů za běh
MIN_TRADE_CZK = 8000     # neobchoduj drobné

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
        return 25, "valuace levná/vhodná k držbě"
    if "FÉR" in v or "FER" in v:
        return 10, "valuace férová"
    if "NAPJAT" in v:
        return -10, "valuace napjatá"
    if "PŘEPÁL" in v or "PREPAL" in v:
        return -28, "valuace přepálená"
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
            d["reasons"].append(f"momentum +{r20:.0f} % za 20 d")
        if (it.get("rel_vol") or 0) >= 1.8:
            d["score"] += 4
            d["reasons"].append("zvýšený objem")
        if (it.get("news_7d") or 0) >= 2:
            d["score"] += 3
        dte = it.get("days_to_earnings")
        if dte is not None and 0 <= dte <= 10:
            d["reasons"].append(f"earnings za {dte} d")

    buys = {(b.get("ticker") or "").upper() for b in sig.get("smart_money_top_buys", [])}
    for tk in buys:
        if tk:
            d = ensure(tk); d["score"] += 15; d["reasons"].append("insideři nakupují (Smart Money)")

    dp = {(x.get("symbol") or "").upper() for x in sig.get("dark_pool", [])[:20]}
    for tk in dp:
        if tk in C:
            C[tk]["score"] += 4
            C[tk]["reasons"].append("vysoký dark-pool objem")

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

        # celý prodej: přepálená valuace / obrat konvikce
        if (verdict and ("PŘEPÁL" in verdict.upper() or "PREPAL" in verdict.upper())) or conv <= SELL_TH:
            reason = (f"Proč prodávám celou pozici: {'valuace je přepálená (drahá)' if verdict and 'PÁL' in verdict.upper() else 'signály se obrátily proti'}"
                      f", konvikce klesla na {conv:.0f}/100. Realizováno {realized:+.0f} Kč ({gain*100:+.0f} %).")
            log_trade("sell", sym, pos["name"], pos["qty"], pr, cu, conv, reason, realized)
            cash += val_czk
            del positions[sym]
            continue
        # fixace části zisku: velký zisk + napjatá valuace
        if gain >= TRIM_GAIN and verdict and "NAPJAT" in verdict.upper() and pos["qty"] > 0:
            qsell = round(pos["qty"] * 0.4, 4)
            if to_czk(qsell * pr, cu) >= MIN_TRADE_CZK:
                rz = to_czk((pr - pos["avg_cost"]) * qsell, cu)
                reason = (f"Prodej části (40 %): zisk +{gain*100:.0f} %, valuace napjatá — fixuji část zisku, "
                          f"zbytek držím. Realizováno {rz:+.0f} CZK.")
                log_trade("trim", sym, pos["name"], qsell, pr, cu, conv, reason, rz)
                cash += to_czk(qsell * pr, cu); pos["qty"] -= qsell
                continue
        # ořez nadváhy
        if weight > MAX_WEIGHT * 1.25:
            target_czk = MAX_WEIGHT * equity
            qsell = round((val_czk - target_czk) / (pr * (fx.get(cu, 1) if cu != BASE_CCY else 1)), 4)
            if qsell > 0 and to_czk(qsell * pr, cu) >= MIN_TRADE_CZK:
                reason = f"Prodej části: váha vzrostla na {weight*100:.0f} %, snižuji k cílovým {MAX_WEIGHT*100:.0f} %."
                log_trade("trim", sym, pos["name"], qsell, pr, cu, conv, reason)
                cash += to_czk(qsell * pr, cu); pos["qty"] -= qsell

    # ── NÁKUPY ──
    equity, _ = equity_now()
    cand = sorted(([tk, d] for tk, d in C.items() if d["score"] >= BUY_TH and tk in prices),
                  key=lambda x: x[1]["score"], reverse=True)
    buys_done = 0
    for tk, d in cand:
        if buys_done >= MAX_BUYS:
            break
        if cash <= equity * CASH_BUFFER:
            break
        pr = prices[tk]; cu = ccy.get(tk, "USD")
        # cílová váha dle konvikce (lineárně 22→60 na 3→10 %)
        tgt_w = min(MAX_WEIGHT, 0.03 + (d["score"] - BUY_TH) / 38.0 * (MAX_WEIGHT - 0.03))
        tgt_czk = tgt_w * equity
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
        reasons = "; ".join(d["reasons"]) or "kompozitní skóre našich signálů"
        reason = (f"Proč nakupuji: {reasons}. Celková konvikce {d['score']:.0f}/100 (čím vyšší, tím silnější "
                  f"signál) → cílová váha {tgt_w*100:.0f} % portfolia, ~{buy_czk:.0f} Kč.")
        log_trade("buy", tk, d["name"], qty, pr, cu, d["score"], reason)
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
    note = _build_note(trades_this_run, equity, start_cap)
    # LLM narativ (gpt-oss na Sparku) — přepíše důvody do čtivé podoby + shrnutí dne
    if trades_this_run and llm_available():
        rows = con.execute("SELECT id,action,symbol,reason FROM trades WHERE ts=? ORDER BY id", (now,)).fetchall()
        if rows:
            listing = "\n".join(f"{i+1}) {r[1].upper()} {r[2]}: {r[3]}" for i, r in enumerate(rows))
            enr = llm_chat(
                "Jsi portfolio manažer AI fondu TRADEZER. Píšeš česky, stručně, sebevědomě, pro zákazníky. Žádné úvahy ani omáčka, jen finální text.",
                f"Přepiš KAŽDÝ důvod obchodu do jedné čtivé věty (max 22 slov), zachovej fakta (ticker, čísla, konvikci). Vrať přesně {len(rows)} řádků, očíslovaných stejně:\n{listing}")
            if enr:
                parsed = _parse_numbered(enr, len(rows))
                for i, row in enumerate(rows):
                    if i in parsed:
                        con.execute("UPDATE trades SET reason=? WHERE id=?", (parsed[i], row[0]))
                con.commit()
            nt = llm_chat(
                "Jsi portfolio manažer AI fondu TRADEZER, píšeš česky pro zákazníky. Žádné úvahy, jen 2 věty.",
                f"Shrň dnešní tah fondu do 2 vět (sebevědomě, lidsky). Hodnota {equity:.0f} CZK ({(equity-start_cap)/start_cap*100:+.1f} %). Dnešní obchody:\n{listing}")
            if nt:
                note = nt
    pos_out = []
    for sym, p in positions.items():
        if p["qty"] <= 1e-9:
            continue
        pr = prices.get(sym, p["avg_cost"]); cu = p["currency"]
        v = to_czk(p["qty"] * pr, cu)
        pos_out.append({"symbol": sym, "name": p["name"], "quantity": round(p["qty"], 4),
                        "avg_cost": round(p["avg_cost"], 4), "currency": cu, "last_price": pr,
                        "value_czk": round(v), "unrealized_czk": round(to_czk((pr - p["avg_cost"]) * p["qty"], cu)),
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
                 "base": BASE_CCY, "as_of": now, "note": note}
    push_mirror(state_out, pos_out, trades_out, snaps_out)
    con.close()


def _build_note(trades, equity, start_cap) -> str:
    pnl = equity - start_cap
    if not trades:
        return f"Dnes bez obchodu — držím stávající pozice. Hodnota {equity:,.0f} CZK ({pnl/start_cap*100:+.1f} %).".replace(",", " ")
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
    return ("Dnes " + "; ".join(parts) + f". Hodnota {equity:,.0f} CZK ({pnl/start_cap*100:+.1f} %).").replace(",", " ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--dry", action="store_true", help="jen spočítej, neukládej/nepushuj")
    ap.add_argument("--loop", type=int, default=0, help="opakuj každých N minut (Spark: 1440 = denně)")
    args = ap.parse_args()
    while True:
        print(f"[{time.strftime('%Y-%m-%d %H:%M')}] TRADEZER investuje -> {BASE} (db {DB_PATH})")
        run(args.push, args.dry)
        if args.loop <= 0:
            break
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
