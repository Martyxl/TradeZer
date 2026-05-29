"""Hybridní predikční model: LLM + historická korelace."""
from dataclasses import dataclass

import structlog

from app.config import settings
from app.llm.client import LLMClassificationResult, llm_client
from app.repositories.news_repository import NewsRepository

log = structlog.get_logger(__name__)

MIN_HISTORICAL_FOR_BLEND = 5


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

        hist_probs, n_hist = await self._get_historical_probs(
            llm_result.categories, ticker_id
        )

        prob_down, prob_neutral, prob_up = self._blend_probs(llm_result, hist_probs, n_hist)

        importance = llm_result.relevance_score * llm_result.llm_confidence * source_weight

        log.info(
            "Prediction complete",
            news_id=news_id,
            ticker=ticker_symbol,
            down=f"{prob_down:.2f}",
            neutral=f"{prob_neutral:.2f}",
            up=f"{prob_up:.2f}",
            n_hist=n_hist,
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
        )
