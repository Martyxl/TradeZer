"use client";

import { useEffect, useState } from "react";
import { LogIn, ArrowDownToLine, ArrowUpToLine, Clock, ChevronDown, ChevronUp } from "lucide-react";

interface EntryLeg {
  n: number; offset_pct: number; offset_p75_pct: number;
  median_min: number; within_30min: number; within_60min: number;
  follow_pct: number; reach_2x_offset_pct: number;
}
interface NyEntry { up: EntryLeg | null; down: EntryLeg | null }

const STATS_KEY: Record<string, string> = { NQ: "nq", GOLD: "gold", XAUUSD: "gold", YM: "ym" };

interface EntryPerf {
  directional_days: number; filled: number; fill_rate: number | null;
  wins: number; win_rate: number | null; avg_pnl_pct: number | null; sum_pnl_pct: number | null;
}
interface HistRow {
  date: string; bias: string; realized: string | null; correct: boolean;
  trust_score: number; entry_filled: boolean | null; entry_win: boolean | null; entry_pnl_pct: number | null;
}

export function EntryCard({ ticker }: { ticker: string }) {
  const [playbook, setPlaybook] = useState<NyEntry | null>(null);
  const [direction, setDirection] = useState<string | null>(null);
  const [perf, setPerf] = useState<EntryPerf | null>(null);
  const [history, setHistory] = useState<HistRow[]>([]);
  const [showHist, setShowHist] = useState(false);

  useEffect(() => {
    const key = STATS_KEY[ticker];
    setPlaybook(null);
    setDirection(null);
    setPerf(null);
    if (key) {
      fetch(`/stats/${key}.json`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((j) => setPlaybook(j?.ny_entry ?? null))
        .catch(() => {});
    }
    fetch(`/api/bias/today?ticker=${ticker}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setDirection(d?.snapshot?.direction ?? d?.live?.direction ?? null))
      .catch(() => {});
    setHistory([]);
    fetch(`/api/bias/stats?ticker=${ticker}&days=90`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setPerf(d?.entry ?? null); setHistory(d?.history ?? []); })
      .catch(() => {});
  }, [ticker]);

  if (!playbook || !direction || direction === "neutral") {
    // Bez směru (neutral bias) nemá entry plán smysl
    return null;
  }
  const leg = direction === "up" ? playbook.up : playbook.down;
  if (!leg) return null;

  const isLong = direction === "up";
  const color = isLong ? "#4ade80" : "#f87171";
  const Icon = isLong ? ArrowUpToLine : ArrowDownToLine;
  const side = isLong ? "LONG" : "SHORT";
  const waitFor = isLong ? "pokles" : "výskok";
  const rr = (leg.follow_pct / leg.offset_pct).toFixed(1);

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4">
      <div className="flex items-center gap-2 mb-3">
        <LogIn size={15} className="text-blue-400" />
        <h2 className="text-sm font-semibold text-white">Entry plán po NY open · {ticker}</h2>
        <span className="text-[10px] text-gray-500">NY open 13:30 UTC (15:30) · z {leg.n} historických dní</span>
      </div>

      <div className="flex flex-wrap items-stretch gap-3">
        <div className="flex items-center gap-2 rounded-lg px-3 py-2 border"
             style={{ borderColor: color + "55", background: color + "14" }}>
          <Icon size={18} style={{ color }} />
          <div>
            <div className="text-sm font-bold" style={{ color }}>{side} setup</div>
            <div className="text-[10px] text-gray-500">ve směru dnešního biasu</div>
          </div>
        </div>

        <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-2 min-w-0">
          <Metric label="Čekej na" value={`${waitFor} +${leg.offset_pct}%`} sub="entry limit od open" />
          <Metric label="Vyplní se do" value={`~${leg.median_min} min`} sub={`${leg.within_60min}% do 60 min`} />
          <Metric label="Follow-through" value={`${leg.follow_pct}%`} sub="medián pohyb potom" accent={color} />
          <Metric label="Poměr R:R" value={`~${rr}:1`} sub="offset vs. follow" accent={color} />
        </div>
      </div>

      {/* Reálná úspěšnost entry plánu (roste den po dni) */}
      {perf && perf.filled > 0 ? (
        <div className="mt-3 pt-3 border-t border-[#232735] flex flex-wrap items-center gap-x-5 gap-y-1 text-[11px]">
          <span className="text-gray-400 font-medium">Úspěšnost plánu (90 dní):</span>
          <span className="text-gray-500">Fill <span className="text-gray-300">{((perf.fill_rate ?? 0) * 100).toFixed(0)}%</span> ({perf.filled}/{perf.directional_days})</span>
          <span className="text-gray-500">Win <span style={{ color: (perf.win_rate ?? 0) >= 0.5 ? "#4ade80" : "#f87171" }}>{((perf.win_rate ?? 0) * 100).toFixed(0)}%</span> ({perf.wins}/{perf.filled})</span>
          {perf.avg_pnl_pct != null && (
            <span className="text-gray-500">Ø P/L <span style={{ color: perf.avg_pnl_pct >= 0 ? "#4ade80" : "#f87171" }}>{perf.avg_pnl_pct > 0 ? "+" : ""}{perf.avg_pnl_pct}%</span></span>
          )}
          {perf.sum_pnl_pct != null && (
            <span className="text-gray-500">Σ <span style={{ color: perf.sum_pnl_pct >= 0 ? "#4ade80" : "#f87171" }}>{perf.sum_pnl_pct > 0 ? "+" : ""}{perf.sum_pnl_pct}%</span></span>
          )}
        </div>
      ) : (
        <p className="mt-3 pt-3 border-t border-[#232735] text-[11px] text-gray-500">
          Úspěšnost entry plánu se začne měřit, jakmile proběhnou první směrové biasy s fillnutým vstupem.
        </p>
      )}

      {/* Historie den po dni */}
      {history.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setShowHist(!showHist)}
            className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-300 transition-colors"
          >
            {showHist ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            Historie plánu ({history.length} dní)
          </button>
          {showHist && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-gray-500 text-[10px] uppercase">
                    <th className="text-left py-1 pr-3">Datum</th>
                    <th className="text-left py-1 pr-3">Bias</th>
                    <th className="text-left py-1 pr-3">Realita</th>
                    <th className="text-center py-1 px-2">Fill</th>
                    <th className="text-center py-1 px-2">Výsledek</th>
                    <th className="text-right py-1 pl-2">P/L</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.date} className="border-t border-[#232735]">
                      <td className="py-1 pr-3 text-gray-400">{h.date.slice(5)}</td>
                      <td className="py-1 pr-3 font-medium" style={{ color: h.bias === "up" ? "#4ade80" : h.bias === "down" ? "#f87171" : "#eab308" }}>
                        {h.bias === "up" ? "LONG" : h.bias === "down" ? "SHORT" : "—"}
                      </td>
                      <td className="py-1 pr-3 text-gray-400">{h.realized ?? "?"}</td>
                      <td className="py-1 px-2 text-center text-gray-500">{h.entry_filled === null ? "—" : h.entry_filled ? "✓" : "no-fill"}</td>
                      <td className="py-1 px-2 text-center font-medium" style={{ color: h.entry_win == null ? "#6b7280" : h.entry_win ? "#4ade80" : "#f87171" }}>
                        {h.entry_win == null ? "—" : h.entry_win ? "WIN" : "LOSS"}
                      </td>
                      <td className="py-1 pl-2 text-right" style={{ color: h.entry_pnl_pct == null ? "#6b7280" : h.entry_pnl_pct >= 0 ? "#4ade80" : "#f87171" }}>
                        {h.entry_pnl_pct == null ? "—" : `${h.entry_pnl_pct > 0 ? "+" : ""}${h.entry_pnl_pct}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <p className="mt-2 text-[10px] text-gray-500 leading-relaxed">
        <Clock size={10} className="inline mr-1" />
        Historicky: po NY open cena v {leg.within_30min}% dní udělá {waitFor} proti biasu do 30 min
        (medián {leg.offset_pct}%, p75 {leg.offset_p75_pct}%) — to je limit pro vstup ve směru biasu.
        P/L počítá pohyb do NY close ve směru biasu včetně zisku z lepší ceny (offsetu).
        Čísla platí <em>pokud</em> bias směr sedí; kombinuj s trust score. Není to obchodní doporučení.
      </p>
    </div>
  );
}

function Metric({ label, value, sub, accent }: {
  label: string; value: string; sub: string; accent?: string;
}) {
  return (
    <div className="rounded-lg bg-[#0f1117] border border-[#2a2d3a] px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-sm font-semibold" style={{ color: accent ?? "#e5e7eb" }}>{value}</div>
      <div className="text-[9px] text-gray-600">{sub}</div>
    </div>
  );
}
