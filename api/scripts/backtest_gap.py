"""Backtest: má RTH gap (open 9:30 ET vs. včerejší close 16:00 ET) prediktivní hodnotu?

A) Chování gapů na dlouhé historii ETF (QQQ ~ NQ, SPY ~ ES, DIA ~ YM): pokračování vs. zavření
   gapu podle velikosti (v ATR) a polohy openu vůči včerejšímu rozsahu.
B) Vztah k našemu BIASu (daily_bias): úspěšnost biasu v NY session, když gap souhlasí / nesouhlasí.

Spuštění (Spark):
  cd ~/tradezer/app/api && DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' ~/tradezer/db.env)" \\
    ~/tradezer/appvenv/bin/python scripts/backtest_gap.py
Bez DATABASE_URL proběhne jen část A.

Pozn.: denní bary Yahoo — open = RTH open, close = RTH close. Ex-dividendové dny dělají malý umělý gap dolů.
"""
from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from datetime import datetime, timezone

import httpx

ETF = {"NQ": "QQQ", "ES": "SPY", "YM": "DIA"}
YEARS = 6
ATR_N = 14
BUCKETS = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.6), (0.6, 1.0), (1.0, 99.0)]


def daily(symbol: str) -> list[dict]:
    p2 = int(time.time())
    p1 = p2 - YEARS * 365 * 86400
    r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                  params={"period1": p1, "period2": p2, "interval": "1d", "includePrePost": "false"},
                  headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    off = res["meta"].get("gmtoffset", 0)
    out = []
    for i, t in enumerate(res["timestamp"]):
        o, h, lo, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, lo, c):
            continue
        out.append({"d": datetime.fromtimestamp(t + off, timezone.utc).date(), "o": o, "h": h, "l": lo, "c": c})
    return out


def features(rows: list[dict]) -> dict:
    """date → featury dne (gap známý při openu) + výsledek NY session."""
    out = {}
    for i in range(ATR_N + 1, len(rows)):
        r, p = rows[i], rows[i - 1]
        trs = [max(rows[j]["h"] - rows[j]["l"], abs(rows[j]["h"] - rows[j - 1]["c"]), abs(rows[j]["l"] - rows[j - 1]["c"]))
               for j in range(i - ATR_N, i)]
        atr = sum(trs) / len(trs)
        gap = r["o"] / p["c"] - 1
        if gap == 0 or atr <= 0:
            continue
        sgn = 1 if gap > 0 else -1
        ny = r["c"] / r["o"] - 1
        out[r["d"]] = {
            "gap": gap, "sgn": sgn, "gap_atr": abs(r["o"] - p["c"]) / atr,
            "pos": "nad včerejším high" if r["o"] > p["h"] else "pod včerejším low" if r["o"] < p["l"] else "uvnitř rozsahu",
            "ny": ny, "cont": (ny > 0) == (sgn > 0) and ny != 0,
            "filled": r["l"] <= p["c"] if sgn > 0 else r["h"] >= p["c"],
            "ny_in_gap_dir": sgn * ny,
        }
    return out


def wilson(k: int, n: int) -> str:
    if not n:
        return "—"
    z, ph = 1.96, k / n
    den = 1 + z * z / n
    mid = (ph + z * z / (2 * n)) / den
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return f"{100 * ph:.0f} % ({100 * (mid - half):.0f}–{100 * (mid + half):.0f})"


def table(title: str, groups: list[tuple[str, list[dict]]]) -> None:
    print(f"\n#### {title}\n")
    print("| skupina | n | pokračuje ve směru gapu (95% CI) | gap se zavřel | Ø pohyb open→close ve směru gapu |")
    print("|---|---:|---|---:|---:|")
    for name, items in groups:
        n = len(items)
        if not n:
            continue
        cont = sum(x["cont"] for x in items)
        filled = sum(x["filled"] for x in items)
        avg = sum(x["ny_in_gap_dir"] for x in items) / n * 100
        print(f"| {name} | {n} | {wilson(cont, n)} | {100 * filled / n:.0f} % | {avg:+.2f} % |")


def part_a(sym: str, f: dict) -> None:
    days = list(f.values())
    up_days = sum(x["ny"] > 0 for x in days)
    print(f"\n### {sym}: {len(days)} obchodních dní ({min(f)} – {max(f)})")
    print(f"Baseline: NY session (open→close) nahoru v {100 * up_days / len(days):.0f} % dní.")
    table("Podle velikosti gapu (v ATR14)",
          [(f"{lo}–{hi if hi < 99 else '∞'} ATR", [x for x in days if lo <= x["gap_atr"] < hi]) for lo, hi in BUCKETS])
    table("Podle polohy openu", [(p, [x for x in days if x["pos"] == p])
                                for p in ("nad včerejším high", "uvnitř rozsahu", "pod včerejším low")])
    table("Podle směru (gap ≥ 0.3 ATR)", [
        ("gap nahoru", [x for x in days if x["sgn"] > 0 and x["gap_atr"] >= 0.3]),
        ("gap dolů", [x for x in days if x["sgn"] < 0 and x["gap_atr"] >= 0.3])])
    table("Velký gap mimo včerejší rozsah", [
        ("≥ 0.6 ATR a open mimo rozsah", [x for x in days if x["gap_atr"] >= 0.6 and x["pos"] != "uvnitř rozsahu"]),
        ("≥ 0.6 ATR a open uvnitř rozsahu", [x for x in days if x["gap_atr"] >= 0.6 and x["pos"] == "uvnitř rozsahu"])])


async def load_biases() -> dict[str, list[dict]]:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import text
    from app.db.engine import engine
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT t.symbol, b.bias_date, b.direction, b.trust_score, b.realized_direction "
            "FROM daily_bias b JOIN tickers t ON t.id = b.ticker_id "
            "WHERE b.direction IN ('up', 'down') ORDER BY b.bias_date"))).all()
    await engine.dispose()
    out: dict[str, list[dict]] = {}
    for sym, d, direction, trust, realized in rows:
        out.setdefault(sym, []).append({"d": d, "dir": direction, "trust": trust or 0, "realized": realized})
    return out


def part_b(sym: str, etf: str, biases: list[dict], f: dict) -> None:
    rows = [{**b, **f[b["d"]]} for b in biases if b["d"] in f]
    print(f"\n### BIAS {sym} × gap {etf}: {len(rows)} dní s up/down biasem a daty "
          f"({len(biases) - len(rows)} bez dat — svátky / mimo rozsah)")
    if not rows:
        return
    for r in rows:
        r["bsgn"] = 1 if r["dir"] == "up" else -1
        r["hit_ny"] = r["bsgn"] * r["ny"] > 0
        r["agree"] = r["bsgn"] == r["sgn"]

    def line(name: str, items: list[dict]) -> None:
        n = len(items)
        if not n:
            return
        hit = sum(x["hit_ny"] for x in items)
        orig = [x for x in items if x["realized"]]
        orig_hit = sum(x["realized"] == x["dir"] for x in orig)
        gap_hit = sum(x["cont"] for x in items)
        print(f"| {name} | {n} | {wilson(hit, n)} | {wilson(gap_hit, n)} | "
              f"{(f'{100 * orig_hit / len(orig):.0f} % (n={len(orig)})') if orig else '—'} |")

    print("\n| skupina | n | bias trefil NY session (95% CI) | samotný gap trefil NY session | bias trefil (náš metric London→close) |")
    print("|---|---:|---|---|---|")
    line("všechny dny", rows)
    line("gap SOUHLASÍ s biasem", [r for r in rows if r["agree"]])
    line("gap PROTI biasu", [r for r in rows if not r["agree"]])
    line("souhlasí, gap ≥ 0.3 ATR", [r for r in rows if r["agree"] and r["gap_atr"] >= 0.3])
    line("proti, gap ≥ 0.3 ATR", [r for r in rows if not r["agree"] and r["gap_atr"] >= 0.3])
    hi = sorted(r["trust"] for r in rows)[len(rows) // 2]
    line(f"trust ≥ medián ({hi:.0f}) a souhlasí", [r for r in rows if r["trust"] >= hi and r["agree"]])
    line(f"trust ≥ medián ({hi:.0f}) a proti", [r for r in rows if r["trust"] >= hi and not r["agree"]])


async def main() -> None:
    feats = {}
    for fut, etf in ETF.items():
        try:
            feats[fut] = features(daily(etf))
        except Exception as e:  # noqa: BLE001
            print(f"{etf}: stažení selhalo ({e})")
    print("## A) Chování RTH gapů (open 9:30 vs. close předchozího dne)")
    for fut, f in feats.items():
        part_a(ETF[fut], f)

    if not os.environ.get("DATABASE_URL"):
        print("\n(DATABASE_URL není nastavená — část B přeskočena)")
        return
    print("\n## B) Gap × náš BIAS (směr v NY session = open 9:30 → close 16:00 ET)")
    biases = await load_biases()
    for fut, etf in ETF.items():
        if fut in biases and fut in feats:
            part_b(fut, etf, biases[fut], feats[fut])


if __name__ == "__main__":
    asyncio.run(main())
