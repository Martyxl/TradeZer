"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { VERDICT_COLOR } from "./BubbleMap";

interface Driver { name: string; value: number | null; contribution: number | null }
interface Detail {
  meta: { as_of_date: string | null; model_version: string; data_source: string; disclaimer: string };
  ticker: string; name: string | null; group_key: string | null;
  valuation_score: number | null; growth_score: number | null; quality_score: number | null;
  revision_score: number | null; trend_score: number | null; composite_score: number | null;
  valuation_verdict: string | null; horizon_verdict: string | null;
  bubble_flag: boolean; confidence: number | null; unreliable: boolean;
  drivers: { positive?: Driver[]; negative?: Driver[] };
  metrics: Record<string, number | null>;
  latest_financials: { period_end: string; revenue: number | null; net_income: number | null; eps_diluted: number | null }[];
  estimates: { horizon: string; metric: string; avg: number | null; n_analysts: number | null }[];
  earnings_history: { period_end: string; surprise_pct: number | null }[];
}

const COMP_LABELS: [keyof Detail, string][] = [
  ["valuation_score", "Valuace"], ["growth_score", "Růst"], ["quality_score", "Kvalita"],
  ["revision_score", "Revize"], ["trend_score", "Trend"],
];

function scoreColor(s: number | null): string {
  if (s == null) return "#4b5563";
  if (s >= 70) return "#4ade80";
  if (s >= 55) return "#84cc16";
  if (s >= 40) return "#f59e0b";
  return "#ef4444";
}

function fmtB(v: number | null): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toFixed(1) + " mld";
  if (abs >= 1e6) return (v / 1e6).toFixed(1) + " mil";
  return v.toFixed(2);
}

export function ValuationDetail({ ticker, onClose }: { ticker: string; onClose: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    setD(null); setErr(false);
    fetch(`/api/valuation/${ticker}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setD).catch(() => setErr(true));
  }, [ticker]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div className="bg-[#12141c] border border-[#2a2d3a] rounded-2xl max-w-2xl w-full p-6 my-8"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-white">{ticker}{d?.name ? ` · ${d.name}` : ""}</h2>
            {d && (
              <div className="flex items-center gap-2 mt-1 text-xs">
                {d.valuation_verdict && (
                  <span className="px-2 py-0.5 rounded font-medium"
                        style={{ background: (VERDICT_COLOR[d.valuation_verdict] ?? "#64748b") + "22",
                                 color: VERDICT_COLOR[d.valuation_verdict] ?? "#9ca3af" }}>
                    {d.valuation_verdict}
                  </span>
                )}
                {d.horizon_verdict && <span className="text-gray-400">{d.horizon_verdict}</span>}
                {d.bubble_flag && <span className="text-red-400">⚠ bublina</span>}
              </div>
            )}
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
        </div>

        {err && <p className="text-sm text-yellow-300">Nedostatek dat pro hodnocení.</p>}
        {!d && !err && <div className="h-40 rounded-xl bg-[#151823] animate-pulse" />}

        {d && (
          <>
            {d.unreliable && (
              <div className="mb-3 rounded-lg border border-yellow-800 bg-yellow-950/40 px-3 py-2 text-[11px] text-yellow-300">
                ⚠ Nízká důvěryhodnost dat (confidence {(d.confidence! * 100).toFixed(0)} %) — verdikt ber s rezervou.
              </div>
            )}

            {/* Rozpad skóre */}
            <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4 mb-3">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-white">Rozpad skóre</h3>
                <span className="text-xs text-gray-500">
                  composite <span className="font-bold" style={{ color: scoreColor(d.composite_score) }}>
                    {d.composite_score?.toFixed(0) ?? "—"}</span> · conf {d.confidence != null ? (d.confidence * 100).toFixed(0) + " %" : "—"}
                </span>
              </div>
              <div className="space-y-2">
                {COMP_LABELS.map(([k, label]) => {
                  const s = d[k] as number | null;
                  return (
                    <div key={k} className="flex items-center gap-2 text-xs">
                      <span className="w-16 shrink-0 text-gray-400">{label}</span>
                      <div className="flex-1 h-2.5 rounded-full bg-[#232735] overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${s ?? 0}%`, background: scoreColor(s) }} />
                      </div>
                      <span className="w-8 text-right font-medium" style={{ color: scoreColor(s) }}>
                        {s?.toFixed(0) ?? "—"}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Drivers */}
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-3">
                <div className="text-[10px] uppercase tracking-wider text-green-400 mb-2">Táhne nahoru</div>
                {(d.drivers.positive ?? []).map((x, i) => (
                  <div key={i} className="flex justify-between text-[11px] text-gray-300 py-0.5">
                    <span>{x.name}</span><span className="text-green-400">+{x.contribution?.toFixed(1)}</span>
                  </div>
                ))}
                {!(d.drivers.positive?.length) && <div className="text-[11px] text-gray-600">—</div>}
              </div>
              <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-3">
                <div className="text-[10px] uppercase tracking-wider text-red-400 mb-2">Táhne dolů</div>
                {(d.drivers.negative ?? []).map((x, i) => (
                  <div key={i} className="flex justify-between text-[11px] text-gray-300 py-0.5">
                    <span>{x.name}</span><span className="text-red-400">{x.contribution?.toFixed(1)}</span>
                  </div>
                ))}
                {!(d.drivers.negative?.length) && <div className="text-[11px] text-gray-600">—</div>}
              </div>
            </div>

            {/* Poslední výsledky + odhady */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-3">
                <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Poslední výsledky (Q)</div>
                {d.latest_financials.slice(0, 3).map((f) => (
                  <div key={f.period_end} className="flex justify-between text-[11px] text-gray-300 py-0.5">
                    <span className="text-gray-500">{f.period_end.slice(0, 7)}</span>
                    <span>tržby {fmtB(f.revenue)} · EPS {f.eps_diluted?.toFixed(2) ?? "—"}</span>
                  </div>
                ))}
              </div>
              <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-3">
                <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Očekávání (konsenzus)</div>
                {d.estimates.filter((e) => e.metric === "eps").slice(0, 3).map((e, i) => (
                  <div key={i} className="flex justify-between text-[11px] text-gray-300 py-0.5">
                    <span className="text-gray-500">EPS {e.horizon}</span>
                    <span>{e.avg?.toFixed(2) ?? "—"} ({e.n_analysts ?? 0} analytiků)</span>
                  </div>
                ))}
              </div>
            </div>

            <p className="text-[10px] text-gray-500 leading-relaxed">
              {d.meta.disclaimer} <span className="text-gray-600">· zdroj {d.meta.data_source} · {d.meta.model_version} · k {d.meta.as_of_date ?? "—"}</span>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
