"""Hybridní predikční model: LLM + historická korelace + pattern memory."""
from dataclasses import dataclass, field

import structlog

from app.config import settings
from app.llm.client import LLMClassificationResult, llm_client
from app.repositories.news_repository import NewsRepository

log = structlog.get_logger(__name__)

MIN_HISTORICAL_FOR_BLEND = 5
MIN_HISTORICAL_FOR_FALLBACK = 3

# Keyword → kategorie pro statistický fallback, když LLM není dostupné.
# Kategorie odpovídají názvům, které LLM běžně přiřazuje (news_categories v DB).
FALLBACK_KEYWORD_CATEGORIES: list[tuple[tuple[str, ...], str]] = [
    (("fed", "fomc", "rate hike", "rate cut", "central bank", "ecb", "boj", "boe", "powell", "lagarde"), "monetary_policy"),
    (("cpi", "inflation", "pce", "deflator"), "inflation"),
    (("payroll", "nfp", "jobless", "unemployment", "jobs report", "adp", "jolts"), "employment"),
    (("housing start", "building permit", "home sales", "housing"), "housing"),
    (("pmi", "ism "), "pmi"),
    (("gdp", "retail sales", "industrial production", "durable goods"), "macro_data"),
    (("war", "iran", "strike", "missile", "ceasefire", "sanction", "geopolit"), "geopolitical"),
    (("oil", "crude", "opec", "natural gas", "energy"), "energy"),
    (("gold", "safe haven", "bullion"), "safe_haven"),
    (("nasdaq", "tech", "apple", "nvidia", "microsoft", "meta", "amazon", "alphabet", "tesla", "ai "), "tech_sector"),
    (("s&p", "dow", "stocks", "equities", "wall street", "index"), "equity_index"),
    (("risk-on", "risk-off", "risk mood", "sentiment", "market wrap"), "risk_sentiment"),
]


def _keyword_categories(title: str, body: str | None) -> list[str]:
    text = (title + " " + (body or "")[:500]).lower()
    return [cat for keywords, cat in FALLBACK_KEYWORD_CATEGORIES if any(k in text for k in keywords)]


@dataclass
class PatternHint:
    """Historický vzor chování trhu pro danou kategorii zprávy."""
    category: str
    sample_count: int
    dominant_direction: str      # "up" / "down" / "neutral"
    dominant_pct: int            # % případů s dominant_direction
    avg_abs_move_30m_pct: float  # průměrný absolutní pohyb za 30min (v %)
    p75_abs_move_30m_pct: float  # 75. percentil absolutního pohybu
    liquidity_grab_rate: float   # podíl událostí s initial fake-out (0–1)
    avg_initial_spike_5m_pct: float | None  # průměrný spike v prvních 5min


@dataclass
class PredictionResult:
    prob_down: float
    prob_neutral: float
    prob_up: float
    confidence: float
    relevance_score: float
    importance_weight: float
    categories: list[str]
    llm_reasoning: str
    model_version: str
    pattern_hints: list[PatternHint] = field(default_factory=list)


class PredictionEngine:
    def __init__(self, repo: NewsRepository):
        self.repo = repo

    def _compute_alpha(self, n_historical: int) -> float:
        """Alpha = váha LLM vs. historická data.
        Drží se vysoko (min 0.6) — historická data jsou zatím příliš neutral-biased
        kvůli prahovému efektu. Alpha klesá max na 0.6 i s velkým počtem vzorků."""
        return max(0.6, 0.85 - 0.01 * min(n_historical, 25))

    def _blend_probs(
        self,
        llm: LLMClassificationResult,
        hist: dict[str, float],
        n_hist: int,
    ) -> tuple[float, float, float]:
        if n_hist < MIN_HISTORICAL_FOR_BLEND:
            return llm.prob_down, llm.prob_neutral, llm.prob_up

        alpha = self._compute_alpha(n_hist)

        # Korekce neutral bias: pokud historická neutral > 0.65, zkrátíme ji
        # k rovnoměrnějšímu rozdělení, aby neovládla výsledek
        hist_neutral = hist.get("neutral", 0.334)
        if hist_neutral > 0.65:
            excess = (hist_neutral - 0.65) / 2
            hist = {
                "down":    hist.get("down", 0.333) + excess,
                "neutral": 0.65,
                "up":      hist.get("up", 0.333) + excess,
            }

        down = alpha * llm.prob_down + (1 - alpha) * hist.get("down", 0.333)
        neutral = alpha * llm.prob_neutral + (1 - alpha) * hist.get("neutral", 0.334)
        up = alpha * llm.prob_up + (1 - alpha) * hist.get("up", 0.333)
        total = down + neutral + up or 1.0
        return down / total, neutral / total, up / total

    async def _get_historical_probs(
        self, categories: list[str], ticker_id: int
    ) -> tuple[dict[str, float], int]:
        direction_counts: dict[str, int] = {"down": 0, "neutral": 0, "up": 0}
        total = 0

        for cat in categories:
            counts = await self.repo.get_historical_direction_by_category(cat, ticker_id)
            for direction, cnt in counts.items():
                if direction in direction_counts:
                    direction_counts[direction] += cnt
                    total += cnt

        if total == 0:
            return {}, 0

        hist_probs = {d: c / total for d, c in direction_counts.items()}
        return hist_probs, total

    async def _get_pattern_hints(
        self, categories: list[str], ticker_id: int
    ) -> list[PatternHint]:
        """Načte historické vzory chování trhu pro dané kategorie."""
        if not categories:
            return []
        try:
            raw = await self.repo.get_category_patterns(
                ticker_id, categories, days=180, min_samples=3
            )
            return [
                PatternHint(
                    category=p["category"],
                    sample_count=p["sample_count"],
                    dominant_direction=p["dominant_direction"],
                    dominant_pct=p["dominant_pct"],
                    avg_abs_move_30m_pct=p["avg_abs_move_30m_pct"],
                    p75_abs_move_30m_pct=p["p75_abs_move_30m_pct"],
                    liquidity_grab_rate=p["liquidity_grab_rate"],
                    avg_initial_spike_5m_pct=p.get("avg_initial_spike_5m_pct"),
                )
                for p in raw
            ]
        except Exception as e:
            log.warning("Pattern hints fetch failed", error=str(e))
            return []

    async def predict(
        self,
        news_id: int,
        ticker_id: int,
        ticker_symbol: str,
        title: str,
        body: str | None,
        source_weight: float,
    ) -> PredictionResult:
        llm_result = llm_client.classify_news(title, body, ticker_symbol)

        # LLM selhalo (vyčerpaný kredit, výpadek API...) → statistický fallback:
        # kategorie z keywords + historické base rates místo uniformních 33/33/33
        if llm_result.llm_confidence == 0.0 and not llm_result.categories:
            return await self._stats_fallback(
                news_id, ticker_id, ticker_symbol, title, body,
                source_weight, llm_result.reasoning,
            )

        hist_probs, n_hist = await self._get_historical_probs(
            llm_result.categories, ticker_id
        )

        prob_down, prob_neutral, prob_up = self._blend_probs(llm_result, hist_probs, n_hist)

        importance = llm_result.relevance_score * llm_result.llm_confidence * source_weight

        # Pattern hints — historické vzory pro tyto kategorie
        pattern_hints = await self._get_pattern_hints(llm_result.categories, ticker_id)

        log.info(
            "Prediction complete",
            news_id=news_id,
            ticker=ticker_symbol,
            down=f"{prob_down:.2f}",
            neutral=f"{prob_neutral:.2f}",
            up=f"{prob_up:.2f}",
            n_hist=n_hist,
            patterns=len(pattern_hints),
        )

        return PredictionResult(
            prob_down=prob_down,
            prob_neutral=prob_neutral,
            prob_up=prob_up,
            confidence=llm_result.llm_confidence,
            relevance_score=llm_result.relevance_score,
            importance_weight=importance,
            categories=llm_result.categories,
            llm_reasoning=llm_result.reasoning,
            model_version=settings.claude_model,
            pattern_hints=pattern_hints,
        )

    async def _stats_fallback(
        self,
        news_id: int,
        ticker_id: int,
        ticker_symbol: str,
        title: str,
        body: str | None,
        source_weight: float,
        llm_error: str,
    ) -> PredictionResult:
        """Predikce bez LLM: kategorie z keywords, pravděpodobnosti z historie."""
        categories = _keyword_categories(title, body)
        hist_probs, n_hist = await self._get_historical_probs(categories, ticker_id)
        pattern_hints = await self._get_pattern_hints(categories, ticker_id)

        if n_hist >= MIN_HISTORICAL_FOR_FALLBACK:
            # Cap na neutral bias stejně jako v _blend_probs
            neutral = min(hist_probs.get("neutral", 0.334), 0.65)
            down = hist_probs.get("down", 0.333)
            up = hist_probs.get("up", 0.333)
            total = down + neutral + up or 1.0
            prob_down, prob_neutral, prob_up = down / total, neutral / total, up / total
            confidence = 0.15
            reasoning = (
                f"⚠ STATISTICKÝ FALLBACK (LLM nedostupné) — kategorie {categories} "
                f"z keywords, pravděpodobnosti z {n_hist} historických reakcí. {llm_error}"
            )
        else:
            prob_down, prob_neutral, prob_up = 0.333, 0.334, 0.333
            confidence = 0.0
            reasoning = (
                f"⚠ FALLBACK bez historie (LLM nedostupné, kategorie {categories or 'nenalezeny'}). "
                f"{llm_error}"
            )

        relevance = 0.4 if categories else 0.2
        log.warning(
            "Stats fallback prediction",
            news_id=news_id, ticker=ticker_symbol,
            categories=categories, n_hist=n_hist,
        )
        return PredictionResult(
            prob_down=prob_down,
            prob_neutral=prob_neutral,
            prob_up=prob_up,
            confidence=confidence,
            relevance_score=relevance,
            importance_weight=relevance * confidence * source_weight,
            categories=categories,
            llm_reasoning=reasoning,
            model_version="stats-fallback-v1",
            pattern_hints=pattern_hints,
        )
