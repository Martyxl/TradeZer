"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import { cn, formatDateTime, importanceBadge } from "@/lib/utils";
import type { NewsItem, TickerImpact } from "@/lib/api";

const SOURCE_LABELS: Record<string, string> = {
  forex_factory: "ForexFactory",
  newsapi: "NewsAPI",
  finnhub: "Finnhub",
  alphavantage: "AlphaVantage",
  rss_reuters: "Reuters",
  rss_ecb: "ECB",
  rss_fxstreet_gold: "FXStreet",
  rss_mining: "Mining.com",
  rss_cnbc_markets: "CNBC",
  rss_cnbc_tech: "CNBC Tech",
};

const FEATURED: { symbol: string; label: string }[] = [
  { symbol: "EURUSD", label: "EUR" },
  { symbol: "XAUUSD", label: "XAU" },
  { symbol: "ES",     label: "ES"  },
  { symbol: "NQ",     label: "NQ"  },
];

const BADGE_STYLE: Record<"S" | "M" | "L", string> = {
  S: "bg-gray-800/80 text-gray-400 border border-gray-700",
  M: "bg-blue-950 text-blue-400 border border-blue-800",
  L: "bg-purple-950 text-purple-400 border border-purple-700",
};

// ─── Left: importance badge ───────────────────────────────────────────
function ImportanceBadge({ weight }: { weight: number | null }) {
  const badge = importanceBadge(weight);
  return (
    <div className={cn(
      "w-9 h-9 rounded-lg flex items-center justify-center text-sm font-black shrink-0 select-none",
      BADGE_STYLE[badge]
    )}>
      {badge}
    </div>
  );
}

// ─── One colored dot + percentage ────────────────────────────────────
function DotPct({
  color, prob, active,
}: {
  color: "up" | "neutral" | "down";
  prob: number;
  active: boolean;
}) {
  const cfg = {
    up: {
      active: "bg-green-500 shadow-[0_0_5px_rgba(34,197,94,0.75)]",
      dim:    "bg-green-950 border border-green-900/60",
      txt:    active ? "text-green-400" : "text-gray-600",
    },
    neutral: {
      active: "bg-yellow-400 shadow-[0_0_5px_rgba(234,179,8,0.75)]",
      dim:    "bg-yellow-950 border border-yellow-900/60",
      txt:    active ? "text-yellow-400" : "text-gray-600",
    },
    down: {
      active: "bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.75)]",
      dim:    "bg-red-950 border border-red-900/60",
      txt:    active ? "text-red-400" : "text-gray-600",
    },
  }[color];

  return (
    <div className="flex items-center gap-0.5" title={`${(prob * 100).toFixed(1)}%`}>
      <div className={cn("w-2 h-2 rounded-full shrink-0", active ? cfg.active : cfg.dim)} />
      <span className={cn("text-[10px] tabular-nums w-[26px]", cfg.txt)}>
        {(prob * 100).toFixed(0)}%
      </span>
    </div>
  );
}

// ─── One ticker row: label + 3 dot+pct ───────────────────────────────
function TickerRow({ label, impact }: { label: string; impact: TickerImpact | undefined }) {
  if (!impact) {
    return (
      <div className="flex items-center gap-1">
        <span className="text-[10px] font-mono w-7 text-gray-700 shrink-0">{label}</span>
        <div className="flex items-center gap-0.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-0.5">
              <div className="w-2 h-2 rounded-full bg-[#1e2130] border border-gray-800/50" />
              <span className="text-[10px] w-[26px] text-gray-800">—</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const { prob_up, prob_neutral, prob_down } = impact;
  const max = Math.max(prob_up, prob_neutral, prob_down);

  return (
    <div className="flex items-center gap-1">
      <span className="text-[10px] font-mono w-7 text-gray-400 shrink-0">{label}</span>
      <div className="flex items-center gap-1">
        <DotPct color="up"      prob={prob_up}      active={prob_up      === max} />
        <DotPct color="neutral" prob={prob_neutral}  active={prob_neutral === max} />
        <DotPct color="down"    prob={prob_down}     active={prob_down    === max} />
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────
interface NewsCardProps {
  item: NewsItem;
}

function ModelTag({ version }: { version?: string }) {
  if (!version) return null;
  let label = version, cls = "bg-gray-800 text-gray-400 border-gray-700";
  if (version.startsWith("local-")) {
    label = "Qwen · local"; cls = "bg-emerald-950/60 text-emerald-300 border-emerald-800";
  } else if (version.includes("haiku")) {
    label = "Haiku"; cls = "bg-blue-950/60 text-blue-300 border-blue-800";
  } else if (version.includes("sonnet")) {
    label = "Sonnet"; cls = "bg-indigo-950/60 text-indigo-300 border-indigo-800";
  } else if (version.includes("fallback")) {
    label = "Fallback"; cls = "bg-yellow-950/60 text-yellow-300 border-yellow-800";
  }
  return (
    <span className={`ml-1 rounded border px-1.5 py-px text-[9px] font-medium ${cls}`} title={version}>
      {label}
    </span>
  );
}

export function NewsCard({ item }: NewsCardProps) {
  const [expanded, setExpanded] = useState(false);
  const pred = item.prediction;
  const impacts = item.ticker_impacts ?? [];
  const impactMap = new Map(impacts.map((t) => [t.symbol, t]));
  const withReasoning = impacts.filter((t) => t.llm_reasoning);

  return (
    <article className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4 transition-all hover:border-gray-600 animate-[fadeIn_0.3s_ease-in-out]">
      {/* ── Main row ── */}
      <div className="flex items-start gap-3">

        {/* Left: importance badge */}
        <div className="shrink-0 pt-0.5">
          <ImportanceBadge weight={item.importance_weight} />
        </div>

        {/* Center: meta + title + main probs */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1 text-[11px] text-gray-500">
            <span>{SOURCE_LABELS[item.source_name] ?? item.source_name}</span>
            <span className="text-gray-700">·</span>
            <span>{formatDateTime(item.published_at)}</span>
            {new Date(item.published_at + (item.published_at.endsWith("Z") ? "" : "Z")).getTime() > Date.now() && (
              <span className="rounded border border-sky-800 bg-sky-950/60 px-1.5 py-px text-[9px] font-medium text-sky-300">
                📅 Nadcházející event
              </span>
            )}
          </div>

          <h3 className="text-sm font-medium text-white leading-snug mb-1.5 line-clamp-2">
            {item.title}
          </h3>

          {pred && (
            <div className="flex items-center gap-2 text-[11px]">
              <span className="text-green-400 font-medium">↑ {(pred.prob_up * 100).toFixed(0)}%</span>
              <span className="text-yellow-400 font-medium">→ {(pred.prob_neutral * 100).toFixed(0)}%</span>
              <span className="text-red-400 font-medium">↓ {(pred.prob_down * 100).toFixed(0)}%</span>
              <ModelTag version={pred.model_version} />
            </div>
          )}
        </div>

        {/* Right: 4-ticker panel — rows with dots+percentages */}
        <div className="shrink-0 flex flex-col gap-1.5 pl-3 border-l border-[#2a2d3a]">
          {FEATURED.map(({ symbol, label }) => (
            <TickerRow
              key={symbol}
              label={label}
              impact={impactMap.get(symbol)}
            />
          ))}
        </div>
      </div>

      {/* ── Expandable reasoning per ticker ── */}
      {withReasoning.length > 0 && (
        <div className="mt-3 pt-2 border-t border-[#2a2d3a]/50">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-300 transition-colors"
          >
            {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            Proč?
          </button>

          {expanded && (
            <div className="mt-2 space-y-2">
              {withReasoning.map((impact) => {
                const badge = importanceBadge(impact.importance_weight);
                const max = Math.max(impact.prob_up, impact.prob_neutral, impact.prob_down);
                return (
                  <div key={impact.symbol} className="rounded-lg bg-[#0f1117] border border-[#2a2d3a] p-3">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-[11px] font-bold font-mono text-gray-300">
                        {impact.symbol}
                      </span>
                      <span className={cn("text-[9px] font-bold px-1 py-0.5 rounded", BADGE_STYLE[badge])}>
                        {badge}
                      </span>
                      <div className="flex items-center gap-1 ml-1">
                        <DotPct color="up"      prob={impact.prob_up}      active={impact.prob_up      === max} />
                        <DotPct color="neutral" prob={impact.prob_neutral}  active={impact.prob_neutral === max} />
                        <DotPct color="down"    prob={impact.prob_down}     active={impact.prob_down    === max} />
                      </div>
                      <span className="ml-auto text-[10px] text-gray-600">
                        {(impact.confidence * 100).toFixed(0)}% conf.
                      </span>
                    </div>
                    <p className="text-[11px] text-gray-400 leading-relaxed">
                      {impact.llm_reasoning}
                    </p>
                  </div>
                );
              })}

              <div className="flex justify-end">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-[11px] text-blue-500 hover:text-blue-400"
                >
                  Zdroj <ExternalLink size={10} />
                </a>
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
