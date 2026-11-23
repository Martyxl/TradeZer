"""Sezónnost pro Přehled (Začátečník): vývoj ceny během kalendářního roku, každý rok zvlášť.

Křivka roku = % změna od posledního close předchozího roku (nebo od prvního obchodního dne v lednu),
x = den v roce (0 = 1. ledna). Rok, pro který chybí začátek dat, se vynechá — useknutá křivka
by začátečníka mátla.
"""
from datetime import date

# Rok bereme, jen když data začínají nejpozději tolik dní po 1. lednu (svátky, první obchodní den).
MAX_START_GAP_DAYS = 10
# Základ z předchozího roku musí být z prosince (nejdřív 20. 12.), jinak je mezi ním a lednem díra.
PREV_FROM_DAY = "12-20"


def year_curves(bars: list[tuple[str, float]], years: list[int]) -> dict[str, list[list[float]]]:
    """bars = [(YYYY-MM-DD, close)] vzestupně → {"2026": [[den_v_roce, % od začátku roku], ...]}."""
    out: dict[str, list[list[float]]] = {}
    for y in years:
        start, prev_from = f"{y}-01-01", f"{y - 1}-{PREV_FROM_DAY}"
        prev = [c for d, c in bars if prev_from <= d < start and c]
        cur = [(d, c) for d, c in bars if d.startswith(f"{y}-") and c]
        if not cur:
            continue
        if prev:
            base, pts = prev[-1], [[0, 0.0]]
        elif (date.fromisoformat(cur[0][0]) - date(y, 1, 1)).days <= MAX_START_GAP_DAYS:
            base, pts = cur[0][1], []
        else:
            continue
        for d, c in cur:
            pts.append([date.fromisoformat(d).timetuple().tm_yday - 1, round((c / base - 1) * 100, 2)])
        out[str(y)] = pts
    return out


def season_years(today: date, n: int = 3) -> list[int]:
    return [today.year - n + 1 + i for i in range(n)]
