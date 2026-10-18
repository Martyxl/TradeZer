"use client";

import { useState } from "react";

export interface OverviewItem {
  ticker: string;
  name: string | null;
  group_key: string | null;
  pctile_pe_fwd: number | null;
  eps_growth_ntm: number | null;
  market_cap: number | null;
  valuation_score: number | null;
  composite_score: number | null;
  valuation_verdict: string | null;
  horizon_verdict: string | null;
  bubble_flag: boolean;
  confidence: number | null;
}

export const VERDICT_COLOR: Record<string, string> = {
  "LEVNÁ": "#4ade80",
  "FÉROVÁ": "#84cc16",
  "NAPJATÁ": "#f59e0b",
  "PŘEPÁLENÁ": "#ef4444",
};

const W = 720, H = 460;
const PAD = { l: 54, r: 24, t: 24, b: 44 };
const PLOT_W = W - PAD.l - PAD.r;
const PLOT_H = H - PAD.t - PAD.b;

// osy: X = pctile_pe_fwd 0..100, Y = eps_growth_ntm (clamp -20..60)
const Y_MIN = -20, Y_MAX = 60;
const xPos = (p: number) => PAD.l + (Math.max(0, Math.min(100, p)) / 100) * PLOT_W;
const yPos = (g: number) => PAD.t + (1 - (Math.max(Y_MIN, Math.min(Y_MAX, g)) - Y_MIN) / (Y_MAX - Y_MIN)) * PLOT_H;

function radius(mc: number | null, maxMc: number): number {
  if (!mc || maxMc <= 0) return 7;
  return 7 + Math.sqrt(mc / maxMc) * 27;
}

interface Placed { it: OverviewItem; cx: number; cy: number; r: number }

// Jen vizuální rozsunutí překrývajících se bublin (max MAX_NUDGE px od skutečné polohy).
const MAX_NUDGE = 16;
export function spread(pts: Placed[]): Placed[] {
  const out = pts.map((p) => ({ ...p, x0: p.cx, y0: p.cy }));
  for (let iter = 0; iter < 40; iter++) {
    for (let i = 0; i < out.length; i++) {
      for (let j = i + 1; j < out.length; j++) {
        const a = out[i], b = out[j];
        let dx = b.cx - a.cx, dy = b.cy - a.cy;
        let d = Math.hypot(dx, dy);
        const min = Math.min(a.r, b.r) + Math.max(a.r, b.r) * 0.45; // povolíme částečný překryv
        if (d >= min) continue;
        if (d < 0.01) { dx = 1; dy = 0; d = 1; }
        const push = (min - d) / 2;
        a.cx -= (dx / d) * push; a.cy -= (dy / d) * push;
        b.cx += (dx / d) * push; b.cy += (dy / d) * push;
      }
    }
    for (const p of out) { // drž se blízko skutečné polohy
      const ox = p.cx - p.x0, oy = p.cy - p.y0, od = Math.hypot(ox, oy);
      if (od > MAX_NUDGE) { p.cx = p.x0 + (ox / od) * MAX_NUDGE; p.cy = p.y0 + (oy / od) * MAX_NUDGE; }
    }
  }
  return out;
}

export function BubbleMap({ items, onSelect }: { items: OverviewItem[]; onSelect: (t: string) => void }) {
  const [hover, setHover] = useState<string | null>(null);
  const plotted = items.filter((i) => i.pctile_pe_fwd != null && i.eps_growth_ntm != null);
  const maxMc = Math.max(...plotted.map((i) => i.market_cap ?? 0), 1);
  // velké dospod, malé nahoře (ať se neztratí); najetá bublina vždy úplně nahoře
  const placed = spread(
    plotted
      .map((it) => ({ it, cx: xPos(it.pctile_pe_fwd!), cy: yPos(it.eps_growth_ntm!), r: radius(it.market_cap, maxMc) }))
      .sort((a, b) => b.r - a.r),
  ).sort((a, b) => (a.it.ticker === hover ? 1 : 0) - (b.it.ticker === hover ? 1 : 0));

  if (plotted.length === 0) {
    return (
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] h-[460px] flex items-center justify-center text-gray-500 text-sm">
        Nedostatek dat pro hodnocení
      </div>
    );
  }

  const x50 = xPos(50), y0 = yPos(0);

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-2 overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[560px]" role="img" aria-label="Bublinová mapa valuace">
        {/* kvadranty */}
        <line x1={x50} y1={PAD.t} x2={x50} y2={PAD.t + PLOT_H} stroke="#2a2d3a" strokeDasharray="4 4" />
        <line x1={PAD.l} y1={y0} x2={PAD.l + PLOT_W} y2={y0} stroke="#2a2d3a" strokeDasharray="4 4" />
        <text x={PAD.l + 6} y={PAD.t + 14} fill="#4b5563" fontSize="10">levné a rostoucí</text>
        <text x={PAD.l + PLOT_W - 6} y={PAD.t + 14} fill="#4b5563" fontSize="10" textAnchor="end">drahé a rostoucí</text>
        <text x={PAD.l + 6} y={PAD.t + PLOT_H - 6} fill="#4b5563" fontSize="10">levné a zpomalující</text>
        <text x={PAD.l + PLOT_W - 6} y={PAD.t + PLOT_H - 6} fill="#4b5563" fontSize="10" textAnchor="end">drahé a zpomalující</text>

        {/* osy popisky */}
        <text x={PAD.l + PLOT_W / 2} y={H - 10} fill="#9ca3af" fontSize="11" textAnchor="middle">
          P/E fwd percentil vůči vlastní historii (0 = levné → 100 = drahé)
        </text>
        <text x={14} y={PAD.t + PLOT_H / 2} fill="#9ca3af" fontSize="11" textAnchor="middle"
              transform={`rotate(-90 14 ${PAD.t + PLOT_H / 2})`}>
          očekávaný růst EPS (NTM, %)
        </text>
        {/* Y ticks */}
        {[-20, 0, 20, 40, 60].map((g) => (
          <text key={g} x={PAD.l - 8} y={yPos(g) + 3} fill="#4b5563" fontSize="9" textAnchor="end">{g}%</text>
        ))}

        {/* bubliny */}
        {placed.map(({ it, cx, cy, r }) => {
          const color = VERDICT_COLOR[it.valuation_verdict ?? ""] ?? "#64748b";
          const dim = it.confidence != null && it.confidence < 0.5;
          return (
            <g key={it.ticker} style={{ cursor: "pointer" }}
               onClick={() => onSelect(it.ticker)}
               onMouseEnter={() => setHover(it.ticker)} onMouseLeave={() => setHover(null)}>
              <circle cx={cx} cy={cy} r={r} fill={color} fillOpacity={dim ? 0.25 : 0.55}
                      stroke={it.bubble_flag ? "#ef4444" : color}
                      strokeWidth={it.bubble_flag ? 2.5 : 1}
                      strokeDasharray={it.bubble_flag ? "3 2" : undefined} />
              <text x={cx} y={cy + 3} fill="#e5e7eb" fontSize="10" textAnchor="middle" fontWeight="600"
                    stroke="#0b0e16" strokeWidth={2.5} paintOrder="stroke">
                {it.ticker}
              </text>
              {it.bubble_flag && (
                <text x={cx + r + 2} y={cy - r} fill="#ef4444" fontSize="11">⚠</text>
              )}
              {hover === it.ticker && (
                <text x={cx} y={cy - r - 5} fill="#e5e7eb" fontSize="10" textAnchor="middle">
                  {it.name?.slice(0, 22)} · comp {it.composite_score?.toFixed(0) ?? "—"}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
