"use client";

import { TrafficLight } from "./TrafficLight";
import { formatPercent } from "@/lib/utils";
import type { DailySummary } from "@/lib/api";

interface DailySummaryCardProps {
  summary: DailySummary | null;
  ticker: string;
}

interface ProbBarProps {
  label: string;
  value: number;
  color: string;
  bgColor: string;
}

function ProbBar({ label, value, color, bgColor }: ProbBarProps) {
  return (
    <div className="flex flex-col items-center gap-2 flex-1">
      <div className="text-xs text-gray-400 font-medium uppercase tracking-wider">{label}</div>
      <div className="relative h-32 w-full rounded-lg overflow-hidden bg-[#0f1117]">
        <div
          className={`absolute bottom-0 left-0 right-0 transition-all duration-700 rounded-lg ${bgColor}`}
          style={{ height: `${value * 100}%` }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`text-lg font-bold ${color}`}>{formatPercent(value)}</span>
        </div>
      </div>
    </div>
  );
}

export function DailySummaryCard({ summary, ticker }: DailySummaryCardProps) {
  if (!summary) {
    return (
      <div className="rounded-2xl border border-[#2a2d3a] bg-[#1a1d27] p-6">
        <h2 className="text-lg font-semibold text-white mb-2">Denní přehled — {ticker}</h2>
        <p className="text-gray-500 text-sm">
          Summary pro dnešní den zatím není k dispozici. Spusťte refresh nebo počkejte na 23:00.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-[#2a2d3a] bg-[#1a1d27] p-6">
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <h2 className="text-lg font-semibold text-white">Denní přehled — {ticker}</h2>
          <p className="text-xs text-gray-500 mt-0.5">{summary.date}</p>
        </div>
        <TrafficLight
          probs={{
            down: summary.overall_prob_down,
            neutral: summary.overall_prob_neutral,
            up: summary.overall_prob_up,
          }}
          size="lg"
          showLabels
        />
      </div>

      {/* Probability bars */}
      <div className="flex gap-3 mb-5">
        <ProbBar
          label="UP"
          value={summary.overall_prob_up}
          color="text-green-400"
          bgColor="bg-green-900/60"
        />
        <ProbBar
          label="NEUTRAL"
          value={summary.overall_prob_neutral}
          color="text-yellow-400"
          bgColor="bg-yellow-900/60"
        />
        <ProbBar
          label="DOWN"
          value={summary.overall_prob_down}
          color="text-red-400"
          bgColor="bg-red-900/60"
        />
      </div>

      {/* Recommendation */}
      {summary.recommendation && (
        <div className="rounded-xl bg-[#0f1117] border border-[#2a2d3a] p-4">
          <p className="text-xs text-gray-500 mb-1.5 font-medium uppercase tracking-wider">
            Doporučení
          </p>
          <p className="text-sm text-gray-200 leading-relaxed">{summary.recommendation}</p>
        </div>
      )}
    </div>
  );
}
