"""Anthropic Claude klient pro news klasifikaci a daily doporučení."""
import json
import uuid
from pathlib import Path

import anthropic
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


_NEWS_CLASSIFIER_PROMPT = _load_prompt("news_classifier.md")
_DAILY_RECOMMENDER_PROMPT = _load_prompt("daily_recommender.md")


class LLMClassificationResult:
    def __init__(self, data: dict):
        self.relevance_score: float = float(data.get("relevance_score", 0.0))
        self.categories: list[str] = data.get("categories", [])
        raw = data.get("raw_direction_probs", {})
        total = sum(raw.values()) or 1.0
        self.prob_down: float = raw.get("down", 0.333) / total
        self.prob_neutral: float = raw.get("neutral", 0.334) / total
        self.prob_up: float = raw.get("up", 0.333) / total
        self.llm_confidence: float = float(data.get("llm_confidence", 0.5))
        self.key_drivers: list[str] = data.get("key_drivers", [])
        self.reasoning: str = data.get("reasoning", "")


class AnthropicLLMClient:
    def __init__(self) -> None:
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            if not settings.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY není nastaven")
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client

    _FAIL_DATA = {
        "relevance_score": 0.0,
        "categories": [],
        "raw_direction_probs": {"down": 0.333, "neutral": 0.334, "up": 0.333},
        "llm_confidence": 0.0,
        "key_drivers": [],
    }

    def classify_news_multi(
        self, title: str, body: str | None, tickers: list[str]
    ) -> dict[str, LLMClassificationResult]:
        """Klasifikuje zprávu pro VŠECHNY tickery jedním LLM callem.

        Úspora: dřív 1 call per ticker (USD event = 6 callů se stejným textem),
        teď 1 call per zpráva. System prompt se cachuje (cache_control).
        """
        request_id = str(uuid.uuid4())[:8]
        log.info("LLM classify start", request_id=request_id, tickers=tickers)

        user_content = f"Tickery: {', '.join(tickers)}\n\nZpráva:\nTitulek: {title}\n"
        if body:
            user_content += f"Obsah: {body[:2000]}"

        def _fail(err: str) -> dict[str, LLMClassificationResult]:
            return {
                t: LLMClassificationResult({**self._FAIL_DATA, "reasoning": f"LLM nedostupný: {err}"})
                for t in tickers
            }

        try:
            client = self._get_client()
            message = client.messages.create(
                model=settings.claude_classifier_model,
                max_tokens=min(300 + 420 * len(tickers), 3000),
                system=[{
                    "type": "text",
                    "text": _NEWS_CLASSIFIER_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_content}],
            )
            raw_text = message.content[0].text.strip()
            # Strip possible markdown code fences
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            data = json.loads(raw_text)
            results = {}
            for t in tickers:
                if isinstance(data.get(t), dict):
                    results[t] = LLMClassificationResult(data[t])
                else:
                    results[t] = LLMClassificationResult(
                        {**self._FAIL_DATA, "reasoning": f"LLM nevrátil klasifikaci pro {t}"}
                    )
            log.info("LLM classify complete", request_id=request_id, tickers=len(results))
            return results
        except Exception as e:
            log.error("LLM classify failed", request_id=request_id, error=str(e))
            return _fail(str(e))

    def classify_news(self, title: str, body: str | None, ticker: str) -> LLMClassificationResult:
        """Klasifikace pro jediný ticker — wrapper nad multi variantou."""
        return self.classify_news_multi(title, body, [ticker])[ticker]

    def generate_daily_recommendation(
        self,
        ticker: str,
        prob_down: float,
        prob_neutral: float,
        prob_up: float,
        top_news: list[dict],
        date_str: str,
    ) -> str:
        request_id = str(uuid.uuid4())[:8]
        log.info("LLM daily recommendation start", request_id=request_id, ticker=ticker)

        drivers_text = "\n".join(
            f"- {n['title']} (váha: {n['weight']:.2f}, směr: {n['direction']})"
            for n in top_news[:5]
        )
        user_content = (
            f"Datum: {date_str}\n"
            f"Ticker: {ticker}\n\n"
            f"Celkové pravděpodobnosti:\n"
            f"  DOWN: {prob_down*100:.1f}%\n"
            f"  NEUTRAL: {prob_neutral*100:.1f}%\n"
            f"  UP: {prob_up*100:.1f}%\n\n"
            f"Nejvlivnější zprávy:\n{drivers_text}"
        )

        try:
            client = self._get_client()
            message = client.messages.create(
                model=settings.claude_model,
                max_tokens=256,
                system=_DAILY_RECOMMENDER_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            result = message.content[0].text.strip()
            log.info("LLM daily recommendation complete", request_id=request_id)
            return result
        except Exception as e:
            log.error("LLM daily recommendation failed", request_id=request_id, error=str(e))
            dominant = max(
                [("DOWN", prob_down), ("NEUTRAL", prob_neutral), ("UP", prob_up)],
                key=lambda x: x[1],
            )
            return (
                f"LLM nedostupný. Dominant signal: {dominant[0]} ({dominant[1]*100:.0f}%). "
                f"Zkontroluj API klíč."
            )


llm_client = AnthropicLLMClient()
