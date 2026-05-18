from datetime import datetime, date
from pydantic import BaseModel, ConfigDict


class TickerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    name: str
    asset_class: str
    neutral_threshold: float
    enabled: bool


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prob_down: float
    prob_neutral: float
    prob_up: float
    confidence: float
    model_version: str
    llm_reasoning: str | None
    created_at: datetime


class TickerImpactOut(BaseModel):
    symbol: str
    prob_down: float
    prob_neutral: float
    prob_up: float
    importance_weight: float
    confidence: float
    llm_reasoning: str | None = None


class NewsItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    body: str | None
    url: str
    published_at: datetime
    source_name: str
    importance_weight: float | None = None
    prediction: PredictionOut | None = None
    ticker_impacts: list[TickerImpactOut] = []


class NewsItemDetail(NewsItemOut):
    categories: list[str] = []
    key_drivers: list[str] = []


class DailySummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticker_id: int
    date: date
    overall_prob_down: float
    overall_prob_neutral: float
    overall_prob_up: float
    recommendation: str | None
    top_drivers: dict
    generated_at: datetime


class RefreshResponse(BaseModel):
    status: str
    stats: dict[str, int]


class HistoryPoint(BaseModel):
    date: date
    realized_direction: str
    predicted_direction: str
    prob_down: float
    prob_neutral: float
    prob_up: float
    accuracy: bool
