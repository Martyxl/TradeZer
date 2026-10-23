"use client";

import { useEffect, useState } from "react";

// Skutečné (forward) výsledky entry plánu z denního biasu — bez pohledu do budoucnosti:
// bias po London open → limit s offsetem proti biasu po NY open → drženo do NY close.
// Zdroj: /api/bias/stats (vyhodnocuje se každý obchodní den po NY close).

interface EntryStats {
  directional_days: number; filled: number; fill_rate: number | null;
  wins: number; win_rate: number | null; avg_pnl_pct: number | null; sum_pnl_pct: number | null;
  t_stat: number | null; since: string | null;
}
interface HistoryRow { date: string; bias: string; entry_filled: boolean | null; entry_pnl_pct: number | null }
interface BiasStats { entry: EntryStats; history: HistoryRow[] }

function EquityCurve({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const W = 320, H = 70, P = 4;
  const min = Math.min(0, ...points), max = Math.max(0, ...points);
  const span = max - min || 1;
  const X = (i: number) => P + (i / (points.length - 1)) * (W - 2 * P);
  const Y = (v: number) => P + (1 - (v - min) / span) * (H - 2 * P);
  const line = points.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const color = last >= 0 ? "#4ade80" : "#f87171";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[70px]" role="img" aria-label="Kumulovaný P/L">
      <line x1={P} x2={W - P} y1={Y(0)} y2={Y(0)} stroke="#2a2d3a" strokeDasharray="3 3" />
      <path d={line} fill="none" stroke={color} strokeWidth={1.6} />
    </svg>
  );
}

export function LiveEntryTracker({ ticker, label }: { ticker: string; label: string }) {
  const [data, setData] = useState<BiasStats | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let alive = true;
    setState("loading");
    fetch(`/api/bias/stats?ticker=${ticker}&days=365`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d: BiasStats) => { if (alive) { setData(d); setState("ready"); } })
      .catch(() => { if (alive) setState("error"); });
    return () => { alive = false; };
  }, [ticker]);

  if (state === "loading") return <div className="h-40 rounded-xl bg-[#151823] animate-pulse border border-[#2a2d3a]" />;
  if (state === "error" || !data) {
    return <p className="text-xs text-gray-500">Live výsledky pro {label} se nepodařilo načíst.</p>;
  }

  const e = data.entry;
  // historie je od nejnovějšího → kumulace chronologicky
  const trades = [...data.history].reverse().filter((h) => h.entry_filled && h.entry_pnl_pct != null);
  let acc = 0;
  const curve = trades.map((h) => (acc += h.entry_pnl_pct as number));
  const t = e.t_stat;
  const verdict = t == null ? { text: "málo obchodů", cls: "text-gray-500" }
    : Math.abs(t) < 2 ? { text: "zatím neprůkazné (šum)", cls: "text-yellow-400" }
    : t > 0 ? { text: "průkazně kladné", cls: "text-green-400" }
    : { text: "průkazně záporné", cls: "text-red-400" };
  const pct = (v: number | null, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)} %`);

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-center">
        <Metric label="Obchodů" value={`${e.filled}`} sub={`z ${e.directional_days} dní se směrem`} />
        <Metric label="Úspěšnost" value={e.win_rate == null ? "—" : `${(e.win_rate * 100).toFixed(0)} %`} sub="obchodů v zisku" />
        <Metric label="Průměr / obchod" value={pct(e.avg_pnl_pct, 3)} sub="před náklady" />
        <Metric label="Součet" value={pct(e.sum_pnl_pct)} sub={e.since ? `od ${e.since}` : ""} />
        <Metric label="Průkaznost (t)" value={t == null ? "—" : t.toFixed(2)} sub={verdict.text} subCls={verdict.cls} />
      </div>
      <div className="mt-3">
        <EquityCurve points={curve} />
        {curve.length < 2 && <p className="text-xs text-gray-500">Křivka se ukáže po prvních obchodech.</p>}
      </div>
    </div>
  );
}

function Metric({ label, value, sub, subCls }: { label: string; value: string; sub?: string; subCls?: string }) {
  return (
    <div>
      <div className="text-lg font-bold text-white">{value}</div>
      <div className="text-[11px] text-gray-500">{label}</div>
      {sub && <div className={`text-[10px] mt-0.5 ${subCls ?? "text-gray-600"}`}>{sub}</div>}
    </div>
  );
}
