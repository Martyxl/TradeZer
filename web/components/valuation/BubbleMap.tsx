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
  zone?: "buy" | "hold" | "avoid" | null;   // rozhodovací zóna (api/app/valuation/zones.py)
  zone_score?: number | null;
  zone_reliable?: boolean;
  zone_note?: string | null;
  growth_basis?: "ntm" | "ttm" | null;
}

/** Popisek zóny; nespolehlivá zóna dostane otazník. */
export function zoneText(it: OverviewItem): string {
  if (!it.zone) return "";
  return ZONE_LABEL[it.zone] + (it.zone_reliable === false ? " (?)" : "");
}

export interface ZoneCurves { buy: [number, number][]; sell: [number, number][] }

export const ZONE_LABEL: Record<string, string> = {
  buy: "nákupní zóna (k prověření)",
  hold: "držet / sledovat",
  avoid: "spíše nepřikupovat / zvážit prodej",
};
export const ZONE_COLOR: Record<string, string> = { buy: "#4ade80", hold: "#9ca3af", avoid: "#f87171" };

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
export interface Cluster { members: Placed[]; cx: number; cy: number; r: number }

// Seskupí bubliny, které se výrazně překrývají (union-find nad skutečnými polohami).
export function cluster(pts: Placed[], overlap = 0.55): Cluster[] {
  const parent = pts.map((_, i) => i);
  const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      const d = Math.hypot(pts[i].cx - pts[j].cx, pts[i].cy - pts[j].cy);
      if (d < (pts[i].r + pts[j].r) * overlap) parent[find(i)] = find(j);
    }
  }
  const groups = new Map<number, Placed[]>();
  pts.forEach((p, i) => groups.set(find(i), [...(groups.get(find(i)) ?? []), p]));
  return [...groups.values()].map((members) => {
    const cx = members.reduce((a, m) => a + m.cx, 0) / members.length;
    const cy = members.reduce((a, m) => a + m.cy, 0) / members.length;
    return { members, cx, cy, r: Math.max(...members.map((m) => m.r)) };
  });
}

export function BubbleMap({ items, onSelect, zones }: { items: OverviewItem[]; onSelect: (t: string) => void; zones?: ZoneCurves | null }) {
  const [hover, setHover] = useState<string | null>(null);
  const plotted = items.filter((i) => i.pctile_pe_fwd != null && i.eps_growth_ntm != null);
  const maxMc = Math.max(...plotted.map((i) => i.market_cap ?? 0), 1);
  const [open, setOpen] = useState<string | null>(null);
  const clusters = cluster(
    plotted
      .map((it) => ({ it, cx: xPos(it.pctile_pe_fwd!), cy: yPos(it.eps_growth_ntm!), r: radius(it.market_cap, maxMc) }))
      .sort((a, b) => b.r - a.r),
  ).sort((a, b) => b.r - a.r);
  const clKey = (c: Cluster) => c.members.map((m) => m.it.ticker).sort().join(",");
  const openCluster = clusters.find((c) => clKey(c) === open);

  if (plotted.length === 0) {
    return (
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] h-[460px] flex items-center justify-center text-gray-500 text-sm">
        Nedostatek dat pro hodnocení
      </div>
    );
  }

  const x50 = xPos(50), y0 = yPos(0);
  // Zóny: nad nákupní křivkou = nákupní zóna, pod prodejní = spíše nepřikupovat (mezi = držet)
  const pts = (c: [number, number][]) => c.map(([p, g]) => `${xPos(p).toFixed(1)},${yPos(g).toFixed(1)}`).join(" ");
  const buy = zones?.buy ?? [], sell = zones?.sell ?? [];
  const buyArea = buy.length > 1
    ? `${pts(buy)} ${xPos(buy[buy.length - 1][0]).toFixed(1)},${yPos(Y_MAX)} ${xPos(buy[0][0]).toFixed(1)},${yPos(Y_MAX)}` : "";
  const sellArea = sell.length > 1
    ? `${pts(sell)} ${xPos(sell[sell.length - 1][0]).toFixed(1)},${yPos(Y_MIN)} ${xPos(sell[0][0]).toFixed(1)},${yPos(Y_MIN)}` : "";

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-2 overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[560px]" role="img" aria-label="Bublinová mapa valuace">
        {/* kvadranty */}
        <line x1={x50} y1={PAD.t} x2={x50} y2={PAD.t + PLOT_H} stroke="#2a2d3a" strokeDasharray="4 4" />
        <line x1={PAD.l} y1={y0} x2={PAD.l + PLOT_W} y2={y0} stroke="#2a2d3a" strokeDasharray="4 4" />
        {buyArea && <polygon points={buyArea} fill="#4ade80" fillOpacity={0.07} />}
        {sellArea && <polygon points={sellArea} fill="#f87171" fillOpacity={0.06} />}
        {buy.length > 1 && <polyline points={pts(buy)} fill="none" stroke="#4ade80" strokeOpacity={0.7} strokeWidth={1.5} strokeDasharray="6 4" />}
        {sell.length > 1 && <polyline points={pts(sell)} fill="none" stroke="#f87171" strokeOpacity={0.7} strokeWidth={1.5} strokeDasharray="6 4" />}
        {buy.length > 1
          ? <text x={PAD.l + 6} y={PAD.t + 14} fill="#4ade80" fillOpacity={0.8} fontSize="10">nákupní zóna (k prověření)</text>
          : <text x={PAD.l + 6} y={PAD.t + 14} fill="#4b5563" fontSize="10">levné a rostoucí</text>}
        <text x={PAD.l + PLOT_W - 6} y={PAD.t + 14} fill="#4b5563" fontSize="10" textAnchor="end">drahé a rostoucí</text>
        <text x={PAD.l + 6} y={PAD.t + PLOT_H - 6} fill="#4b5563" fontSize="10">levné a zpomalující</text>
        {sell.length > 1
          ? <text x={PAD.l + PLOT_W - 6} y={PAD.t + PLOT_H - 6} fill="#f87171" fillOpacity={0.8} fontSize="10" textAnchor="end">spíše nepřikupovat / zvážit prodej</text>
          : <text x={PAD.l + PLOT_W - 6} y={PAD.t + PLOT_H - 6} fill="#4b5563" fontSize="10" textAnchor="end">drahé a zpomalující</text>}

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
        {clusters.map((c) => {
          if (c.members.length === 1) {
            const { it, cx, cy, r } = c.members[0];
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
                    {it.name?.slice(0, 22)} · comp {it.composite_score?.toFixed(0) ?? "—"}{it.zone ? ` · ${zoneText(it)}` : ""}
                  </text>
                )}
              </g>
            );
          }
          const k = clKey(c), sel = open === k;
          return (
            <g key={k} style={{ cursor: "pointer" }} data-testid="bubble-cluster"
               onClick={() => setOpen(sel ? null : k)}>
              <circle cx={c.cx} cy={c.cy} r={Math.max(c.r, 14)} fill="#64748b" fillOpacity={0.35}
                      stroke={sel ? "#e5e7eb" : "#94a3b8"} strokeWidth={sel ? 2 : 1.5} strokeDasharray="4 3" />
              <text x={c.cx} y={c.cy + 4} fill="#e5e7eb" fontSize="12" textAnchor="middle" fontWeight="700"
                    stroke="#0b0e16" strokeWidth={2.5} paintOrder="stroke">
                {c.members.length}×
              </text>
            </g>
          );
        })}
      </svg>
      {openCluster && (
        <div className="mt-2 rounded-lg border border-[#2a2d3a] bg-[#10131c] p-3" data-testid="cluster-list">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-400">
              {openCluster.members.length} firem se překrývá — klikni na firmu pro detail
            </span>
            <button onClick={() => setOpen(null)} className="text-xs text-gray-500 hover:text-gray-300">zavřít ✕</button>
          </div>
          <ul className="grid gap-1 sm:grid-cols-2">
            {[...openCluster.members].sort((a, b) => (b.it.composite_score ?? -1) - (a.it.composite_score ?? -1)).map(({ it }) => (
              <li key={it.ticker}>
                <button onClick={() => onSelect(it.ticker)}
                  className="w-full flex items-center gap-2 rounded px-2 py-1 text-left text-xs hover:bg-[#1a1d27]">
                  <span className="inline-block h-2 w-2 rounded-full"
                        style={{ background: VERDICT_COLOR[it.valuation_verdict ?? ""] ?? "#64748b" }} />
                  <span className="font-semibold text-white">{it.ticker}</span>
                  <span className="truncate text-gray-400">{it.name}</span>
                  {it.zone && (
                    <span className="text-[10px]" title={it.zone_note ?? undefined}
                          style={{ color: it.zone_reliable === false ? "#6b7280" : ZONE_COLOR[it.zone] }}>{zoneText(it)}</span>
                  )}
                  <span className="ml-auto text-gray-500">{it.composite_score?.toFixed(0) ?? "—"}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
