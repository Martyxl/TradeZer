"use client";

import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Minus, Zap, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type CategoryPattern } from "@/lib/api";

const CATEGORY_LABELS: Record<string, string> = {
  monetary_policy:     "Monetary Policy",
  inflation:           "Inflation",
  employment:          "Employment",
  gdp:                 "GDP",
  pmi:                 "PMI",
  fed_speech:          "Fed Speech",
  ecb_speech:          "ECB Speech",
  geopolitical:        "Geopolitical",
  trade_balance:       "Trade Balance",
  central_bank_minutes:"CB Minutes",
  retail_sales:        "Retail Sales",
  housing:             "Housing",
  consumer_confidence: "Consumer Conf.",
  energy:              "Energy",
  earnings:            "Earnings",
  risk_sentiment:      "Risk Sentiment",
  fiscal_policy:       "Fiscal Policy",
  surprise_beat:       "Surprise Beat",
  surprise_miss:       "Surprise Miss",
  safe_haven:          "Safe Haven",
  equity_index:        "Equity Index",
  tech_sector:         "Tech Sector",
};

function DirectionBadge({ dir, pct }: { dir: "up" | "neutral" | "down"; pct: number }) {
  if (dir === "up") return (
    <span className="inline-flex items-center gap-0.5 text-green-400 font-semibold text-xs">
      <TrendingUp size={11} />
      {pct}%
    </span>
  );
  if (dir === "down") return (
    <span className="inline-flex items-center gap-0.5 text-red-400 font-semibold text-xs">
      <TrendingDown size={11} />
      {pct}%
    </span>
  );
  return (
    <span className="inline-flex items-center gap-0.5 text-yellow-400 font-semibold text-xs">
      <Minus size={11} />
      {pct}%
    </span>
  );
}

function PatternRow({ p }: { p: CategoryPattern }) {
  const label = CATEGORY_LABELS[p.category] ?? p.category;
  const grabPct = Math.round(p.liquidity_grab_rate * 100);
  const highGrab = grabPct >= 25;

  return (
    <div className="grid grid-cols-[140px_1fr_1fr_1fr_auto] items-center gap-x-4 gap-y-0 py-2 border-b border-[#1e2130]/80 last:border-0 text-[11px]">

      {/* Category */}
      <span className="text-gray-300 font-medium truncate" title={p.category}>
        {label}
      </span>

      {/* Dominant direction */}
      <div className="flex items-center gap-2">
        <DirectionBadge dir={p.dominant_direction} pct={p.dominant_pct} />
        <span className="text-gray-600 text-[10px]">
          ({p.direction_distribution.up}↑ {p.direction_distribution.neutral}→ {p.direction_distribution.down}↓)
        </span>
      </div>

      {/* Typical 30min move */}
      <div className="text-gray-300 tabular-nums">
        <span className="text-gray-500 mr-1">avg</span>
        <span className="text-white font-medium">{p.avg_abs_move_30m_pct.toFixed(2)}%</span>
        <span className="text-gray-600 mx-1">·</span>
        <span className="text-gray-500 mr-1">p75</span>
        <span className="font-medium text-blue-300">{p.p75_abs_move_30m_pct.toFixed(2)}%</span>
      </div>

      {/* Liquidity grab */}
      <div className={cn("flex items-center gap-1", highGrab ? "text-orange-400" : "text-gray-600")}>
        <Zap size={10} className={highGrab ? "text-orange-400" : "text-gray-700"} />
        <span className={cn("tabular-nums", highGrab ? "font-semibold" : "")}>
          {grabPct}%
        </span>
        <span className="text-[10px] hidden sm:inline">
          {p.liquidity_grab_samples > 0 ? "fake-out" : ""}
        </span>
      </div>

      {/* Sample count */}
      <span className="text-gray-600 text-[10px] tabular-nums text-right">
        {p.sample_count}×
      </span>
    </div>
  );
}

interface PatternPanelProps {
  ticker: string;
}

export function PatternPanel({ ticker }: PatternPanelProps) {
  const [patterns, setPatterns] = useState<CategoryPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.getPatterns(ticker)
      .then((res) => setPatterns(res.patterns))
      .catch(() => setPatterns([]))
      .finally(() => setLoading(false));
  }, [ticker]);

  // Show top 5 by default, all when expanded
  const visible = expanded ? patterns : patterns.slice(0, 5);

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Pattern Memory
          </h2>
          <span className="text-[11px] text-gray-600 font-mono">{ticker}</span>
          {patterns.length > 0 && (
            <span className="text-[10px] text-gray-700">· 180 dní</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="group relative">
            <Info size={12} className="text-gray-600 cursor-help" />
            <div className="absolute right-0 top-4 w-56 rounded-lg border border-[#2a2d3a] bg-[#0f1117] p-2.5 text-[10px] text-gray-400 leading-relaxed z-10 hidden group-hover:block">
              <strong className="text-gray-200">Jak číst tabulku:</strong>
              <br />· avg/p75 = typický pohyb ceny za 30 min po zprávě
              <br />· <span className="text-orange-400">⚡ fake-out</span> = cena nejdřív šla opačně (likviditní past)
              <br />· číslo vpravo = počet historických vzorků
            </div>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-8 rounded bg-[#0f1117] animate-pulse" />
          ))}
        </div>
      ) : patterns.length === 0 ? (
        <div className="py-6 text-center text-gray-600 text-xs">
          Zatím nedostatek dat pro {ticker} — vzory se budou plnit po každém cron cyklu.
        </div>
      ) : (
        <>
          {/* Column headers */}
          <div className="grid grid-cols-[140px_1fr_1fr_1fr_auto] gap-x-4 mb-1 text-[10px] text-gray-600 uppercase tracking-wider">
            <span>Kategorie</span>
            <span>Směr (historicky)</span>
            <span>Pohyb 30min</span>
            <span>Fake-out</span>
            <span className="text-right">N</span>
          </div>

          <div>
            {visible.map((p) => (
              <PatternRow key={p.category} p={p} />
            ))}
          </div>

          {patterns.length > 5 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-2 text-[11px] text-blue-500 hover:text-blue-400 transition-colors"
            >
              {expanded ? "Zobrazit méně" : `Zobrazit všechny (${patterns.length})`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
