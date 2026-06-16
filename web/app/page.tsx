"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { TickerFilter } from "@/components/TickerFilter";
import { DailySummaryCard } from "@/components/DailySummaryCard";
import { NewsCard } from "@/components/NewsCard";
import { MarketHoursBar } from "@/components/MarketHoursBar";
import { PatternPanel } from "@/components/PatternPanel";
import { api, type Ticker, type NewsItem, type DailySummary } from "@/lib/api";

export default function DashboardPage() {
  const [tickers, setTickers] = useState<Ticker[]>([]);
  const [selectedTicker, setSelectedTicker] = useState("EURUSD");
  const [news, setNews] = useState<NewsItem[]>([]);
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
  const refreshMsgTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadTickers = useCallback(async () => {
    try {
      const data = await api.getTickers();
      setTickers(data);
    } catch {
      // Use default ticker list on error
    }
  }, []);

  const loadData = useCallback(async (ticker: string) => {
    setLoading(true);
    setError(null);
    try {
      const [newsData, summaryData] = await Promise.allSettled([
        api.getNews(ticker, undefined, 25),
        api.getDailySummary(ticker),
      ]);
      setNews(newsData.status === "fulfilled" ? newsData.value : []);
      setSummary(summaryData.status === "fulfilled" ? summaryData.value : null);
    } catch (e) {
      setError("Nepodařilo se načíst data. Je backend spuštěný?");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshMsg(null);
    if (refreshMsgTimer.current) clearTimeout(refreshMsgTimer.current);
    try {
      const result = await api.triggerRefresh();
      if (result.status === "rate_limited") {
        setRefreshMsg(`Počkej ${result.retry_after_seconds}s`);
      } else {
        const n = result.new_items ?? 0;
        const p = result.predicted ?? 0;
        setRefreshMsg(n > 0 ? `+${n} zpráv, ${p} predikcí` : "Žádné nové zprávy");
        await loadData(selectedTicker);
      }
    } catch {
      setRefreshMsg("Chyba refreshe");
    } finally {
      setRefreshing(false);
      refreshMsgTimer.current = setTimeout(() => setRefreshMsg(null), 4000);
    }
  }, [refreshing, selectedTicker, loadData]);

  useEffect(() => {
    loadTickers();
  }, [loadTickers]);

  useEffect(() => {
    loadData(selectedTicker);
  }, [selectedTicker, loadData]);

  // SSE live updates
  useEffect(() => {
    const es = new EventSource(`/api/stream?ticker=${selectedTicker}`);
    es.onmessage = (e) => {
      try {
        const item = JSON.parse(e.data) as NewsItem;
        setNews((prev) => {
          if (prev.find((n) => n.id === item.id)) return prev;
          return [item, ...prev.slice(0, 24)];
        });
      } catch {
        // ignore malformed SSE frames
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [selectedTicker]);

  return (
    <div className="space-y-6">
      {/* Market hours timeline */}
      <MarketHoursBar />

      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <TickerFilter
          tickers={
            tickers.length > 0
              ? tickers
              : [
                  { id: 1, symbol: "EURUSD", name: "EUR/USD", asset_class: "forex", neutral_threshold: 0.002, enabled: true },
                  { id: 4, symbol: "XAUUSD", name: "XAU/USD", asset_class: "commodity", neutral_threshold: 0.002, enabled: true },
                  { id: 5, symbol: "BTCUSD", name: "BTC/USD", asset_class: "crypto", neutral_threshold: 0.005, enabled: true },
                  { id: 6, symbol: "ES", name: "E-mini S&P 500", asset_class: "futures", neutral_threshold: 0.002, enabled: true },
                  { id: 7, symbol: "NQ", name: "E-mini Nasdaq 100", asset_class: "futures", neutral_threshold: 0.003, enabled: true },
                ]
          }
          selected={selectedTicker}
          onChange={setSelectedTicker}
        />
        <div className="flex items-center gap-2">
          {refreshMsg && (
            <span className="text-xs text-gray-400 animate-fade-in">{refreshMsg}</span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="flex items-center gap-2 rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-3 py-1.5 text-sm text-gray-300 hover:text-white hover:border-gray-500 transition-all disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            {refreshing ? "Stahuji…" : "Refresh"}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-800 bg-red-950/50 p-4 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Daily Summary */}
      <DailySummaryCard summary={summary} ticker={selectedTicker} />

      {/* Pattern Memory */}
      <PatternPanel ticker={selectedTicker} />

      {/* News feed */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">
          Zprávy · {selectedTicker}
          <span className="ml-2 text-gray-600 font-normal">({news.length})</span>
        </h2>

        {loading && news.length === 0 ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-[#1a1d27] animate-pulse border border-[#2a2d3a]" />
            ))}
          </div>
        ) : news.length === 0 ? (
          <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-8 text-center text-gray-500 text-sm">
            Žádné zprávy pro {selectedTicker} dnes. Spusťte refresh nebo zkontrolujte API klíče.
          </div>
        ) : (
          <div className="space-y-3">
            {news.map((item) => (
              <NewsCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
