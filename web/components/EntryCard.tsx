"use client";

import { useEffect, useState } from "react";
import { LogIn, ArrowDownToLine, ArrowUpToLine, Clock } from "lucide-react";

interface EntryLeg {
  n: number; offset_pct: number; offset_p75_pct: number;
  median_min: number; within_30min: number; within_60min: number;
  follow_pct: number; reach_2x_offset_pct: number;
}
interface NyEntry { up: EntryLeg | null; down: EntryLeg | null }

const STATS_KEY: Record<string, string> = { NQ: "nq", GOLD: "gold", XAUUSD: "gold", YM: "ym" };

export function EntryCard({ ticker }: { ticker: string }) {
  const [playbook, setPlaybook] = useState<NyEntry | null>(null);
  const [direction, setDirection] = useState<string | null>(null);

  useEffect(() => {
    const key = STATS_KEY[ticker];
    setPlaybook(null);
    setDirection(null);
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

      <p className="mt-3 text-[10px] text-gray-500 leading-relaxed">
        <Clock size={10} className="inline mr-1" />
        Historicky: po NY open cena v {leg.within_30min}% dní udělá {waitFor} proti biasu do 30 min
        (medián {leg.offset_pct}%, p75 {leg.offset_p75_pct}%) — to je limit pro vstup ve směru biasu.
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
