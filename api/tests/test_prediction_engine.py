"""Unit testy pro PredictionEngine."""
import pytest
from unittest.mock import patch, MagicMock

from app.services.prediction_engine import PredictionEngine
from app.llm.client import LLMClassificationResult


def _make_llm_result(**kwargs) -> LLMClassificationResult:
    defaults = {
        "relevance_score": 0.8,
        "categories": ["monetary_policy"],
        "raw_direction_probs": {"down": 0.2, "neutral": 0.3, "up": 0.5},
        "llm_confidence": 0.8,
        "key_drivers": ["ECB hawkish"],
        "reasoning": "Test reason",
    }
    defaults.update(kwargs)
    return LLMClassificationResult(defaults)


class TestPredictionEngineAlpha:
    def setup_method(self):
        self.engine = PredictionEngine(repo=MagicMock())

    def test_alpha_starts_at_0_7(self):
        assert self.engine._compute_alpha(0) == pytest.approx(0.7)

    def test_alpha_decreases_with_history(self):
        alpha_5 = self.engine._compute_alpha(5)
        alpha_20 = self.engine._compute_alpha(20)
        assert alpha_5 > alpha_20

    def test_alpha_minimum_is_0_3(self):
        assert self.engine._compute_alpha(100) == pytest.approx(0.3)

    def test_alpha_at_20_samples(self):
        expected = max(0.3, 0.7 - 0.02 * 20)
        assert self.engine._compute_alpha(20) == pytest.approx(expected)


class TestPredictionEngineBlend:
    def setup_method(self):
        self.engine = PredictionEngine(repo=MagicMock())

    def test_pure_llm_when_no_history(self):
        llm = _make_llm_result()
        down, neutral, up = self.engine._blend_probs(llm, {}, 0)
        assert down == pytest.approx(llm.prob_down)
        assert up == pytest.approx(llm.prob_up)

    def test_blend_normalizes_to_1(self):
        llm = _make_llm_result()
        hist = {"down": 0.4, "neutral": 0.3, "up": 0.3}
        down, neutral, up = self.engine._blend_probs(llm, hist, 10)
        assert down + neutral + up == pytest.approx(1.0, abs=1e-6)

    def test_blend_with_enough_history(self):
        llm = _make_llm_result(
            raw_direction_probs={"down": 0.1, "neutral": 0.1, "up": 0.8}
        )
        hist = {"down": 0.9, "neutral": 0.05, "up": 0.05}
        down, neutral, up = self.engine._blend_probs(llm, hist, 10)
        # UP should be lower than pure LLM because history says DOWN
        assert up < llm.prob_up


class TestLLMClassificationResult:
    def test_normalizes_probabilities(self):
        result = LLMClassificationResult({
            "raw_direction_probs": {"down": 2.0, "neutral": 1.0, "up": 1.0},
        })
        total = result.prob_down + result.prob_neutral + result.prob_up
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_defaults_on_empty(self):
        result = LLMClassificationResult({})
        assert result.relevance_score == 0.0
        assert result.llm_confidence == 0.5
        assert result.categories == []
