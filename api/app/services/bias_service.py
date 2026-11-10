"""Denní BIAS: agregace ranních predikcí -> směr dne, snapshot v London open,
vyhodnocení proti realitě (pohyb London open -> 17:00 ET; v létě 07:00 -> 21:00 UTC) a statistika úspěšnosti.

Obchodní den = 22:00 UTC předchozího dne až 22:00 UTC. Snapshot se dělá při
prvním zpracování po 07:00 UTC (London open) z predikcí zpráv publikovaných
od začátku obchodního dne.
"""
import asyncio
import bisect
import math
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyBias, NewsItem, NewsPrediction, Ticker
from app.models.news import DirectionEnum, MarketReaction, NewsCategory, NewsItemCategory
from app.sources.yahoo_finance_adapter import YahooFinanceAdapter, _close_before, _find_close_at

log = structlog.get_logger(__name__)

# Časy session jsou v MÍSTNÍM čase burzy — v UTC se posouvají s letním/zimním časem
# (London open 07:00 UTC v létě / 08:00 v zimě, NY cash open 13:30 / 14:30, close 17:00 ET = 21:00 / 22:00).
# Dřív byly pevně v UTC → v zimě vstup o hodinu dřív než skutečný NY open.
_LONDON = ZoneInfo("Europe/London")
_NY = ZoneInfo("America/New_York")
LONDON_OPEN_LOCAL = time(8, 0)
NY_OPEN_LOCAL = time(9, 30)    # otevření US cash trhu
NY_CLOSE_LOCAL = time(17, 0)   # denní uzávěrka futures (CME)


def _local_to_utc(d: date, t: time, tz: ZoneInfo) -> datetime:
    """Místní čas burzy v daný den → naivní UTC datetime."""
    return datetime.combine(d, t, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)


def london_open_utc(d: date) -> datetime:
    return _local_to_utc(d, LONDON_OPEN_LOCAL, _LONDON)


def ny_open_utc(d: date) -> datetime:
    return _local_to_utc(d, NY_OPEN_LOCAL, _NY)


def ny_close_utc(d: date) -> datetime:
    return _local_to_utc(d, NY_CLOSE_LOCAL, _NY)

DAY_START_SHIFT_H = 2  # 22:00 UTC = začátek obchodního dne

# Doporučený entry offset (%) proti biasu po NY open — z historického playbooku
# (medián protipohybu). Fallback = 2× neutral_threshold.
ENTRY_OFFSET_PCT = {
    "NQ":     {"up": 0.25, "down": 0.20},
    "YM":     {"up": 0.22, "down": 0.20},
    "XAUUSD": {"up": 0.27, "down": 0.23},
    "ES":     {"up": 0.15, "down": 0.13},
}


def _entry_offset(symbol: str, direction: str, neutral_threshold: float) -> float:
    m = ENTRY_OFFSET_PCT.get(symbol)
    if m and direction in m:
        return m[direction]
    return round(neutral_threshold * 2 * 100, 3)


def _trading_day(now: datetime) -> date:
    return (now + timedelta(hours=DAY_START_SHIFT_H)).date()


def _day_start_utc(tday: date) -> datetime:
    """Začátek okna zpráv pro obchodní den. Pondělí počítá od PÁTEČNÍHO close (22:00 UTC) —
    zprávy o víkendu ovlivní, kde se trh v neděli večer / v pondělí otevře, takže patří do
    pondělního biasu (dřív se počítaly až od neděle 22:00 a všechny víkendové zprávy se ztratily)."""
    back = 3 if tday.weekday() == 0 else 1
    return datetime.combine(tday - timedelta(days=back), time(22, 0), tzinfo=None)


async def compute_bias(session: AsyncSession, ticker: Ticker, tday: date,
                       until: datetime | None = None) -> dict:
    """Váženě zprůměruje predikce zpráv obchodního dne (volitelně do času `until`)."""
    start = _day_start_utc(tday)
    stmt = (
        select(NewsPrediction, NewsItem.published_at)
        .join(NewsItem, NewsItem.id == NewsPrediction.news_id)
        .where(NewsPrediction.ticker_id == ticker.id)
        .where(NewsItem.published_at >= start)
        .where(NewsPrediction.confidence > 0.0)
    )
    if until is not None:
        stmt = stmt.where(NewsItem.published_at <= until)
    rows = (await session.execute(stmt)).all()

    if not rows:
        # Žádná důvěryhodná predikce (0 zpráv nebo všechny s confidence 0)
        # → nelze určit směr. "unknown" ≠ neutral (neutral = trh čekaně plochý).
        return {"n_news": 0, "prob_down": 0.333, "prob_neutral": 0.334, "prob_up": 0.333,
                "direction": "unknown", "trust_score": 0.0, "avg_confidence": 0.0}

    tw = td = tn = tu = tc = 0.0
    for pred, _pub in rows:
        w = max(pred.confidence, 0.05)
        tw += w
        td += w * pred.prob_down
        tn += w * pred.prob_neutral
        tu += w * pred.prob_up
        tc += pred.confidence
    down, neutral, up = td / tw, tn / tw, tu / tw
    total = down + neutral + up or 1.0
    down, neutral, up = down / total, neutral / total, up / total

    direction = max([("down", down), ("neutral", neutral), ("up", up)], key=lambda x: x[1])[0]
    n = len(rows)
    avg_conf = tc / n

    # Důvěryhodnost: počet zpráv (max při 8+), průměrná confidence,
    # a vyhraněnost rozdělení (1 - normalizovaná entropie)
    probs = [p for p in (down, neutral, up) if p > 0]
    entropy = -sum(p * math.log(p) for p in probs) / math.log(3)
    trust = 100 * (0.35 * min(n / 8, 1.0) + 0.35 * avg_conf + 0.30 * (1 - entropy))

    return {
        "n_news": n,
        "prob_down": round(down, 4), "prob_neutral": round(neutral, 4), "prob_up": round(up, 4),
        "direction": direction,
        "trust_score": round(trust, 1),
        "avg_confidence": round(avg_conf, 3),
    }


# ---------------------------------------------------------------- bias v2 (stínový režim)
# Rozbor 11/2026: tipy zpráv celkově ~51 % (hod mincí), trust score antikorelovaný se skutečnou
# úspěšností. Walk-forward test: bias složený JEN ze zpráv v kategoriích, jejichž tipy v minulosti
# prokazatelně trefovaly reakci trhu, trefil London→close v 59,8 % (51,3–67,8 %, 132 dní).
# Běží vedle současného biasu; na dashboard až po ověření na nových dnech.
V2_MIN_N = 30          # min. počet vyhodnocených směrových tipů v kategorii


def _wilson_low(k: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    return ((p + z * z / (2 * n)) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def _tip(up: float, down: float, neutral: float) -> str:
    return "up" if up >= max(down, neutral) else "down" if down >= max(up, neutral) else "neutral"


async def load_category_hits(session: AsyncSession) -> list[tuple[datetime, str, bool]]:
    """[(published_at, kategorie, trefil?)] pro směrové tipy zpráv se směrovou reakcí trhu, seřazeno."""
    rows = (await session.execute(
        select(NewsItem.published_at, NewsCategory.name, NewsPrediction.prob_up, NewsPrediction.prob_down,
               NewsPrediction.prob_neutral, MarketReaction.realized_direction)
        .join(NewsPrediction, NewsPrediction.news_id == NewsItem.id)
        .join(MarketReaction, (MarketReaction.news_id == NewsPrediction.news_id)
              & (MarketReaction.ticker_id == NewsPrediction.ticker_id))
        .join(NewsItemCategory, NewsItemCategory.news_id == NewsItem.id)
        .join(NewsCategory, NewsCategory.id == NewsItemCategory.category_id)
        .where(MarketReaction.skip_reason.is_(None))
        .where(MarketReaction.realized_direction.in_([DirectionEnum.UP, DirectionEnum.DOWN]))
    )).all()
    out = []
    for pub, cat, up, down, neu, rd in rows:
        tip = _tip(up, down, neu)
        if tip == "neutral" or pub is None:
            continue
        real = rd.value if hasattr(rd, "value") else str(rd).lower()
        out.append((pub, cat, tip == real))
    out.sort(key=lambda x: x[0])
    return out


def verified_categories(hits: list[tuple[datetime, str, bool]], before: datetime) -> set[str]:
    """Kategorie s trefovaností prokazatelně > 50 % (dolní mez 95% Wilsona) — jen ze zpráv před `before`."""
    idx = bisect.bisect_left(hits, (before,), key=lambda x: (x[0],))
    stat: dict[str, list[int]] = {}
    for _pub, cat, ok in hits[:idx]:
        a = stat.setdefault(cat, [0, 0])
        a[0] += ok
        a[1] += 1
    return {c for c, (k, n) in stat.items() if n >= V2_MIN_N and _wilson_low(k, n) > 0.5}


def v2_signal(preds: list[tuple[float, float, float]]) -> dict:
    """preds = [(prob_up, prob_down, confidence)] → směr ze znaménka váženého up−down."""
    tw = sum(max(c, 0.05) for _u, _d, c in preds)
    if not preds or tw <= 0:
        return {"direction": "none", "score": None, "n": 0}
    s = sum(max(c, 0.05) * (u - d) for u, d, c in preds) / tw
    return {"direction": "up" if s > 0 else "down" if s < 0 else "none", "score": round(s, 4), "n": len(preds)}


async def compute_bias_v2(session: AsyncSession, ticker_id: int, tday: date, good: set[str],
                          until: datetime | None = None) -> dict:
    """Bias v2 pro obchodní den: zprávy od začátku dne do `until` (London open) jen z ověřených kategorií."""
    if not good:
        return {"direction": "none", "score": None, "n": 0, "cats": ""}
    until = until or london_open_utc(tday)
    rows = (await session.execute(
        select(NewsPrediction.id, NewsPrediction.prob_up, NewsPrediction.prob_down, NewsPrediction.confidence,
               NewsCategory.name)
        .join(NewsItem, NewsItem.id == NewsPrediction.news_id)
        .join(NewsItemCategory, NewsItemCategory.news_id == NewsItem.id)
        .join(NewsCategory, NewsCategory.id == NewsItemCategory.category_id)
        .where(NewsPrediction.ticker_id == ticker_id)
        .where(NewsItem.published_at >= _day_start_utc(tday), NewsItem.published_at <= until)
        .where(NewsPrediction.confidence > 0.0)
        .where(NewsCategory.name.in_(sorted(good)))
    )).all()
    preds: dict[int, tuple[float, float, float]] = {}
    used: set[str] = set()
    for pid, up, down, conf, cat in rows:
        preds[pid] = (up, down, conf)
        used.add(cat)
    return {**v2_signal(list(preds.values())), "cats": ",".join(sorted(used))[:200]}


async def fill_v2_missing(session: AsyncSession, limit: int = 400) -> int:
    """Doplní bias v2 ke snapshotům, které ho nemají (nové dny i zpětně). Kategorie se pro každý den
    učí jen ze zpráv PŘED začátkem toho dne → žádný pohled do budoucnosti."""
    rows = [b for b in (await session.execute(
        select(DailyBias).where(DailyBias.v2_direction.is_(None)).order_by(DailyBias.bias_date)
    )).scalars().all() if b.bias_date.weekday() < 5][:limit]
    if not rows:
        return 0
    hits = await load_category_hits(session)
    cache: dict[date, set[str]] = {}
    for b in rows:
        if b.bias_date not in cache:
            cache[b.bias_date] = verified_categories(hits, _day_start_utc(b.bias_date))
        r = await compute_bias_v2(session, b.ticker_id, b.bias_date, cache[b.bias_date])
        b.v2_direction, b.v2_score, b.v2_n_news, b.v2_cats = r["direction"], r["score"], r["n"], r["cats"]
    await session.commit()
    log.info("Bias v2 doplněn", rows=len(rows))
    return len(rows)


async def ensure_snapshots(session: AsyncSession, tickers: list[Ticker]) -> int:
    """Po London open vytvoří denní snapshot BIASu (jednou za den a ticker)."""
    now = datetime.utcnow()
    tday = _trading_day(now)
    if tday.weekday() >= 5:   # sobota/neděle: trh zavřený, bias by nešel vyhodnotit
        return 0
    # Snapshot až po London open daného obchodního dne
    london = london_open_utc(tday)
    if now < london:
        return 0

    created = 0
    for ticker in tickers:
        existing = await session.scalar(
            select(DailyBias).where(DailyBias.ticker_id == ticker.id, DailyBias.bias_date == tday)
        )
        if existing:
            continue
        bias = await compute_bias(session, ticker, tday, until=london)
        session.add(DailyBias(
            ticker_id=ticker.id, bias_date=tday,
            prob_down=bias["prob_down"], prob_neutral=bias["prob_neutral"], prob_up=bias["prob_up"],
            direction=bias["direction"], trust_score=bias["trust_score"],
            n_news=bias["n_news"], avg_confidence=bias["avg_confidence"],
        ))
        created += 1
        log.info("Bias snapshot created", ticker=ticker.symbol, date=str(tday), **bias)
    if created:
        await session.commit()
    return created


def _record_ny_path(bias: DailyBias, bars: list[dict], symbol: str, neutral_threshold: float) -> None:
    """Zaznamená protipohyb/pohyb po NY open (9:30 ET) relativně ke směru biasu.

    adverse = jak daleko šla cena PROTI biasu (kam dát limit entry),
    favorable = jak daleko ve směru biasu. Neutral bias cestu nepočítá.
    Zároveň vyhodnotí entry plán (limit na offset, hold do close).
    """
    if bias.direction not in ("up", "down"):
        return
    ny_open_dt = ny_open_utc(bias.bias_date).replace(tzinfo=timezone.utc).timestamp()
    ny_close_dt = ny_close_utc(bias.bias_date).replace(tzinfo=timezone.utc).timestamp()
    seg = [b for b in bars if ny_open_dt <= b["t"] <= ny_close_dt and b.get("high") and b.get("low")]
    if len(seg) < 6:
        return
    ref = seg[0]["close"]
    if not ref:
        return
    bias.ny_open_price = round(ref, 4)

    if bias.direction == "down":
        # adverse = nejvyšší high nad ref; favorable = nejnižší low pod ref
        adv_bar = max(seg, key=lambda b: b["high"])
        adverse = (adv_bar["high"] - ref) / ref
        favorable = (ref - min(b["low"] for b in seg)) / ref
    else:
        adv_bar = min(seg, key=lambda b: b["low"])
        adverse = (ref - adv_bar["low"]) / ref
        favorable = (max(b["high"] for b in seg) - ref) / ref

    bias.ny_adverse_pct = round(adverse * 100, 4)
    bias.ny_favorable_pct = round(favorable * 100, 4)
    bias.ny_adverse_min = int((adv_bar["t"] - ny_open_dt) / 60)

    # Entry plán: limit na offset proti biasu. Fill když protipohyb dosáhl offsetu.
    # P/L = pohyb od SKUTEČNÉ vstupní ceny (limit) do NY close ve směru biasu. Dřív se bral pohyb
    # od London open (realized_pct) + offset → započítával se i pohyb PŘED vstupem (P/L nadsazené).
    offset = _entry_offset(symbol, bias.direction, neutral_threshold)
    bias.entry_filled = (bias.ny_adverse_pct >= offset)
    if bias.entry_filled:
        bias_sign = 1 if bias.direction == "up" else -1
        entry = ref * (1 - bias_sign * offset / 100)
        close = seg[-1]["close"]
        bias.entry_pnl_pct = round(bias_sign * (close - entry) / entry * 100, 4)
        bias.entry_win = bias.entry_pnl_pct > 0
    else:
        bias.entry_pnl_pct = None
        bias.entry_win = None


def _record_ny_session(bias: DailyBias, bars: list[dict], neutral_threshold: float) -> None:
    """Realita NY session: close 1. baru po 9:30 ET → close posledního baru před 16:00 ET.
    Hlavní metrika úspěšnosti biasu — bez premarketu/gapu, který je v London→close."""
    o = ny_open_utc(bias.bias_date).replace(tzinfo=timezone.utc).timestamp()
    c = ny_close_utc(bias.bias_date).replace(tzinfo=timezone.utc).timestamp()
    seg = [b for b in bars if o <= b["t"] < c and b.get("close")]
    if len(seg) < 6:
        return
    pct = (seg[-1]["close"] - seg[0]["close"]) / seg[0]["close"]
    thr = neutral_threshold * 2
    bias.ny_realized_direction = "up" if pct > thr else ("down" if pct < -thr else "neutral")
    bias.ny_realized_pct = round(pct, 5)


async def evaluate_pending(session: AsyncSession, ticker_map: dict[int, Ticker], limit: int = 30) -> int:
    """Doplhní realitu ke snapshotům po NY close: London→close (07:00 → 21:00 UTC) i NY session.
    Starší vyhodnocené dny bez NY session metriky se dopočítají (dokud jsou v dosahu Yahoo 5m dat)."""
    now = datetime.utcnow()
    today = _trading_day(now)
    # Nejnovější napřed a jen v dosahu Yahoo 5m dat (~60 dní). Dřív: prvních 10 BEZ řazení → staré,
    # už nevyhodnotitelné řádky (červenec) navždy obsadily všech 10 míst a od 27. 7. se nevyhodnotil
    # ani jeden den.
    stmt = (select(DailyBias)
            .where(or_(DailyBias.realized_direction.is_(None), DailyBias.ny_realized_direction.is_(None)),
                   DailyBias.bias_date >= today - timedelta(days=58))
            .order_by(DailyBias.bias_date.desc()))
    # Víkendové dny nemají NY session → nevyhodnotitelné, nesmí zabírat místa ve frontě.
    pending = [b for b in (await session.execute(stmt)).scalars().all() if b.bias_date.weekday() < 5][:limit]

    yahoo = YahooFinanceAdapter()
    evaluated = 0
    for b in pending:
        # Hodnotit až po NY close daného dne
        if b.bias_date > today or (b.bias_date == today and now < ny_close_utc(b.bias_date)):
            continue
        ticker = ticker_map.get(b.ticker_id)
        if not ticker:
            continue
        try:
            bars = await asyncio.to_thread(yahoo.fetch_day_bars, ticker.symbol, b.bias_date)
            if b.realized_direction is not None:
                # Už vyhodnoceno London→close — jen doplň NY session metriku
                _record_ny_session(b, bars, ticker.neutral_threshold)
                if b.ny_realized_direction is not None:
                    evaluated += 1
                continue
            p_open = _find_close_at(bars, london_open_utc(b.bias_date).replace(tzinfo=timezone.utc), 60)
            p_close = _find_close_at(bars, ny_close_utc(b.bias_date).replace(tzinfo=timezone.utc), 60)
            if not p_open or not p_close:
                continue
            pct = (p_close - p_open) / p_open
            thr = ticker.neutral_threshold * 2  # celodenní pohyb — přísnější práh
            realized = "up" if pct > thr else ("down" if pct < -thr else "neutral")
            b.realized_direction = realized
            b.realized_pct = round(pct, 5)
            b.evaluated_at = now

            # Intradenní cesta po NY open + vyhodnocení entry plánu
            _record_ny_path(b, bars, ticker.symbol, ticker.neutral_threshold)
            _record_ny_session(b, bars, ticker.neutral_threshold)
            evaluated += 1
            log.info("Bias evaluated", ticker=ticker.symbol, date=str(b.bias_date),
                     bias=b.direction, realized=realized, pct=round(pct * 100, 2))
        except Exception as e:
            log.warning("Bias evaluation failed", ticker_id=b.ticker_id, error=str(e))
    evaluated += await _evaluate_old_hourly(session, ticker_map, today, now)
    if evaluated:
        await session.commit()
    return evaluated


async def _evaluate_old_hourly(session: AsyncSession, ticker_map: dict[int, Ticker], today: date,
                               now: datetime, limit: int = 5) -> int:
    """Dny starší než dosah Yahoo 5m dat (např. celý srpen 2026) → London open → close z HODINOVÝCH
    barů (Yahoo ~730 dní). NY session / entry potřebují 5 min, ty zůstanou prázdné."""
    stmt = (select(DailyBias)
            .where(DailyBias.realized_direction.is_(None),
                   DailyBias.bias_date < today - timedelta(days=58),
                   DailyBias.bias_date >= today - timedelta(days=700))
            .order_by(DailyBias.bias_date.desc()))
    pending = [b for b in (await session.execute(stmt)).scalars().all() if b.bias_date.weekday() < 5][:limit]
    yahoo = YahooFinanceAdapter()
    done = 0
    for b in pending:
        ticker = ticker_map.get(b.ticker_id)
        if not ticker:
            continue
        try:
            bars = await asyncio.to_thread(yahoo.fetch_hour_bars, ticker.symbol, b.bias_date)
            p_open = _close_before(bars, london_open_utc(b.bias_date).replace(tzinfo=timezone.utc), 60)
            p_close = _close_before(bars, ny_close_utc(b.bias_date).replace(tzinfo=timezone.utc), 60)
            if not p_open or not p_close:
                continue
            pct = (p_close - p_open) / p_open
            thr = ticker.neutral_threshold * 2
            b.realized_direction = "up" if pct > thr else ("down" if pct < -thr else "neutral")
            b.realized_pct = round(pct, 5)
            b.evaluated_at = now
            done += 1
            log.info("Bias evaluated (1h)", ticker=ticker.symbol, date=str(b.bias_date), pct=round(pct * 100, 2))
        except Exception as e:  # noqa: BLE001
            log.warning("Bias hourly evaluation failed", ticker_id=b.ticker_id, error=str(e))
    return done
