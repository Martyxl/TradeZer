"use client";

import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, MoveRight, Target } from "lucide-react";

interface BiasSnapshot {
  prob_down: number; prob_neutral: number; prob_up: number;
  direction: string; trust_score: number; n_news: number;
  snapshot_at: string;
  realized_direction: string | null; realized_pct: number | null;
}
interface BiasLive {
  prob_down: number; prob_neutral: number; prob_up: number;
  direction: string; trust_score: number; n_news: number;
}
interface BiasToday {
  ticker: string; date: string;
  snapshot: BiasSnapshot | null; live: BiasLive;
}
interface BiasStats {
  total: number; accuracy: number | null;
  directional_total: number; directional_accuracy: number | null;
}

const DIR_META: Record<string, { label: string; color: string; Icon: typeof TrendingUp }> = {
  up: { label: "LONG", color: "#4ade80", Icon: TrendingUp },
  down: { label: "SHORT", color: "#f87171", Icon: TrendingDown },
  neutral: { label: "NEUTRAL", color: "#eab308", Icon: MoveRight },
};

function trustLabel(score: number): { text: string; color: string } {
  if (score >= 65) return { text: "Vysoká důvěryhodnost", color: "#4ade80" };
  if (score >= 40) return { text: "Střední důvěryhodnost", color: "#eab308" };
  return { text: "Nízká důvěryhodnost", color: "#f87171" };
}

function ProbRow({ b }: { b: { prob_down: number; prob_neutral: number; prob_up: number } }) {
  return (
    <div className="flex h-2.5 rounded-full overflow-hidden bg-[#232735]">
      <div style={{ width: `${b.prob_down * 100}%`, background: "#f87171" }} />
      <div style={{ width: `${b.prob_neutral * 100}%`, background: "#64748b" }} />
      <div style={{ width: `${b.prob_up * 100}%`, background: "#4ade80" }} />
    </div>
  );
}

export function BiasCard({ ticker }: { ticker: string }) {
  const [data, setData] = useState<BiasToday | null>(null);
  const [stats, setStats] = useState<BiasStats | null>(null);

  useEffect(() => {
    setData(null);
    fetch(`/api/bias/today?ticker=${ticker}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setData)
      .catch(() => {});
    fetch(`/api/bias/stats?ticker=${ticker}&days=30`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setStats)
      .catch(() => {});
  }, [ticker]);

  if (!data) return null;
  const snap = data.snapshot;
  const bias = snap ?? data.live;
  const meta = DIR_META[bias.direction] ?? DIR_META.neutral;
  const trust = trustLabel(bias.trust_score);
  const { Icon } = meta;

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Target size={15} className="text-blue-400" />
          <h2 className="text-sm font-semibold text-white">Dnešní BIAS · {ticker}</h2>
          <span className="text-[10px] text-gray-500">
            {snap ? `snapshot London open (${bias.n_news} zpráv)` : `průběžný (${bias.n_news} zpráv) — snapshot v 9:00`}
          </span>
        </div>

        <div className="ml-auto flex items-center gap-2 rounded-lg px-3 py-1.5 border"
             style={{ borderColor: meta.color + "55", background: meta.color + "14" }}>
          <Icon size={16} style={{ color: meta.color }} />
          <span className="text-sm font-bold" style={{ color: meta.color }}>{meta.label}</span>
          <span className="text-[10px]" style={{ color: trust.color }}>· {trust.text} ({bias.trust_score.toFixed(0)})</span>
        </div>
      </div>

      <div className="mt-3">
        <ProbRow b={bias} />
        <div className="mt-1 flex justify-between text-[10px] text-gray-500">
          <span className="text-red-400">↓ {(bias.prob_down * 100).toFixed(0)}%</span>
          <span>→ {(bias.prob_neutral * 100).toFixed(0)}%</span>
          <span className="text-green-400">↑ {(bias.prob_up * 100).toFixed(0)}%</span>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500">
        {snap?.realized_direction && (
          <span>
            Realita dne:{" "}
            <span style={{ color: DIR_META[snap.realized_direction]?.color }}>
              {DIR_META[snap.realized_direction]?.label}
              {snap.realized_pct != null && ` (${(snap.realized_pct * 100).toFixed(2)} %)`}
            </span>
            {" — "}
            {snap.realized_direction === snap.direction ? "✓ bias seděl" : "✗ bias neseděl"}
          </span>
        )}
        {stats && stats.total > 0 && (
          <span>
            Úspěšnost 30 dní: <span className="text-gray-300">{((stats.accuracy ?? 0) * 100).toFixed(0)} %</span>
            {stats.directional_total > 0 && (
              <> · směrové biasy: <span className="text-gray-300">
                {((stats.directional_accuracy ?? 0) * 100).toFixed(0)} %</span> ({stats.directional_total}×)</>
            )}
          </span>
        )}
        {stats && stats.total === 0 && <span>Statistika úspěšnosti se začne tvořit od zítřka.</span>}
      </div>
    </div>
  );
}
