const API_BASE = "";

export interface Ticker {
  id: number;
  symbol: string;
  name: string;
  asset_class: string;
  neutral_threshold: number;
  enabled: boolean;
}

export interface Prediction {
  id: number;
  prob_down: number;
  prob_neutral: number;
  prob_up: number;
  confidence: number;
  model_version: string;
  llm_reasoning: string | null;
  created_at: string;
}

export interface TickerImpact {
  symbol: string;
  prob_down: number;
  prob_neutral: number;
  prob_up: number;
  importance_weight: number;
  confidence: number;
  llm_reasoning: string | null;
}

export interface NewsItem {
  id: number;
  title: string;
  body: string | null;
  url: string;
  published_at: string;
  source_name: string;
  importance_weight: number | null;
  prediction: Prediction | null;
  ticker_impacts: TickerImpact[];
}

export interface NewsItemDetail extends NewsItem {
  categories: string[];
  key_drivers: string[];
}

export interface DailySummary {
  id: number;
  ticker_id: number;
  date: string;
  overall_prob_down: number;
  overall_prob_neutral: number;
  overall_prob_up: number;
  recommendation: string | null;
  top_drivers: Record<string, unknown>;
  generated_at: string;
}

export interface HistoryPoint {
  date: string;
  realized_direction: string;
  predicted_direction: string;
  prob_down: number;
  prob_neutral: number;
  prob_up: number;
  accuracy: boolean;
}

export interface CategoryStat {
  total: number;
  correct: number;
  accuracy: number | null;
  up: number;
  neutral: number;
  down: number;
}

export interface AccuracyStats {
  ticker: string;
  days: number;
  total: number;
  correct: number;
  accuracy: number | null;
  by_category: Record<string, CategoryStat>;
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  getTickers: () => fetchJson<Ticker[]>("/api/tickers"),

  getNews: (ticker: string, date?: string, limit = 25, offset = 0) => {
    const params = new URLSearchParams({ ticker, limit: String(limit), offset: String(offset) });
    if (date) params.set("date", date);
    return fetchJson<NewsItem[]>(`/api/news?${params}`);
  },

  getNewsDetail: (id: number) => fetchJson<NewsItemDetail>(`/api/news/${id}`),

  getDailySummary: (ticker: string, date?: string) => {
    const params = new URLSearchParams({ ticker });
    if (date) params.set("date", date);
    return fetchJson<DailySummary>(`/api/summary/daily?${params}`);
  },

  getHistory: (ticker: string, days = 90) =>
    fetchJson<HistoryPoint[]>(`/api/history?ticker=${ticker}&days=${days}`),

  getStats: (ticker: string, days = 90) =>
    fetchJson<AccuracyStats>(`/api/stats?ticker=${ticker}&days=${days}`),
};
