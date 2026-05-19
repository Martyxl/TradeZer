"use client";

import { useEffect, useState } from "react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  Tooltip, Cell, PieChart, Pie,
} from "recharts";
import { api, type HistoryPoint, type AccuracyStats } from "@/lib/api";

const DIR_COLORS: Record<string, string> = {
  up: "#22c55e",
  neutral: "#eab308",
  down: "#ef4444",
};

const TICKERS = ["EURUSD", "XAUUSD", "BTCUSD", "ES", "NQ"];

export default function HistoryPage() {
  const [data, setData] = useState<HistoryPoint[]>([]);
  const [stats, setStats] = useState<AccuracyStats | null>(null);
  const [ticker, setTicker] = useState("EURUSD");
  const [days, setDays] = useState(90);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      api.getHistory(ticker, days),
      api.getStats(ticker, days),
    ]).then(([histRes, statsRes]) => {
      setData(histRes.status === "fulfilled" ? histRes.value : []);
      setStats(statsRes.status === "fulfilled" ? statsRes.value : null);
    }).finally(() => setLoading(false));
  }, [ticker, days]);

  const accuracy = data.length > 0
    ? (data.filter((d) => d.accuracy).length / data.length) * 100
    : 0;

  const dirDist = ["up", "neutral", "down"].map((dir) => ({
    name: dir.toUpperCase(),
    value: data.filter((d) => d.realized_direction === dir).length,
    fill: DIR_COLORS[dir],
  }));

  const byDate = Array.from(
    data.reduce((acc, d) => {
      const key = d.date;
      if (!acc.has(key)) acc.set(key, { date: key, correct: 0, total: 0 });
      const entry = acc.get(key)!;
      entry.total++;
      if (d.accuracy) entry.correct++;
      return acc;
    }, new Map<string, { date: string; correct: number; total: number }>())
  )
    .map(([, v]) => ({ ...v, accuracy: v.total > 0 ? (v.correct / v.total) * 100 : 0 }))
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-30);

  const catRows = stats
    ? Object.entries(stats.by_category)
        .filter(([, v]) => v.total >= 2)
        .sort((a, b) => b[1].total - a[1].total)
        .slice(0, 15)
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-xl font-bold text-white">Historie predikcí</h1>
        <div className="ml-auto flex gap-3">
          <select
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-3 py-1.5 text-sm text-gray-300"
          >
            {TICKERS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-3 py-1.5 text-sm text-gray-300"
          >
            {[30, 60, 90, 180, 365].map((d) => (
              <option key={d} value={d}>{d} dní</option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Predikcí s reakcí", value: stats?.total ?? data.length },
          { label: "Správných", value: stats?.correct ?? data.filter((d) => d.accuracy).length },
          { label: "Celková přesnost", value: stats?.accuracy != null ? `${(stats.accuracy * 100).toFixed(1)}%` : data.length > 0 ? `${accuracy.toFixed(1)}%` : "—" },
          { label: "Kategorií", value: catRows.length },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4 text-center">
            <div className="text-2xl font-bold text-white">{value}</div>
            <div className="text-xs text-gray-500 mt-1">{label}</div>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-64 rounded-xl bg-[#1a1d27] animate-pulse border border-[#2a2d3a]" />
          ))}
        </div>
      ) : data.length === 0 ? (
        <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-8 text-center text-gray-500 text-sm">
          Žádná historická data. Predikce se začnou kalibrovat po první dávce zpráv (tržní reakce se zaznamenávají 15 min po vydání zprávy).
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Accuracy over time */}
            <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-5">
              <h2 className="text-sm font-semibold text-gray-300 mb-4">Přesnost v čase (posl. 30 dní)</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={byDate}>
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#6b7280" }} tickLine={false} />
                  <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 10, fill: "#6b7280" }} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8 }}
                    formatter={(v: number) => [`${v.toFixed(0)}%`, "Přesnost"]}
                  />
                  <Bar dataKey="accuracy" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Direction distribution */}
            <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-5">
              <h2 className="text-sm font-semibold text-gray-300 mb-4">Rozdělení realizovaných směrů</h2>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={dirDist}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ name, percent }) =>
                      percent > 0.05 ? `${name} ${(percent * 100).toFixed(0)}%` : ""
                    }
                  >
                    {dirDist.map((entry) => (
                      <Cell key={entry.name} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Category accuracy table */}
          {catRows.length > 0 && (
            <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-5">
              <h2 className="text-sm font-semibold text-gray-300 mb-4">
                Přesnost per kategorie — {ticker}
                <span className="ml-2 text-gray-600 font-normal text-xs">min. 2 záznamy</span>
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b border-[#2a2d3a]">
                      <th className="text-left py-2 pr-4 font-medium">Kategorie</th>
                      <th className="text-right py-2 px-3 font-medium">Vzorků</th>
                      <th className="text-right py-2 px-3 font-medium">Přesnost</th>
                      <th className="text-right py-2 px-3 font-medium text-green-500">↑ UP</th>
                      <th className="text-right py-2 px-3 font-medium text-yellow-500">→ NEUT</th>
                      <th className="text-right py-2 px-3 font-medium text-red-500">↓ DOWN</th>
                    </tr>
                  </thead>
                  <tbody>
                    {catRows.map(([cat, v]) => {
                      const acc = v.accuracy;
                      const accColor = acc == null ? "text-gray-600"
                        : acc >= 0.6 ? "text-green-400"
                        : acc >= 0.45 ? "text-yellow-400"
                        : "text-red-400";
                      const dominant = v.up >= v.neutral && v.up >= v.down ? "up"
                        : v.down >= v.neutral ? "down" : "neutral";
                      return (
                        <tr key={cat} className="border-b border-[#2a2d3a]/40 hover:bg-white/[0.02]">
                          <td className="py-2 pr-4 text-gray-300 font-mono">{cat}</td>
                          <td className="text-right px-3 text-gray-500">{v.total}</td>
                          <td className={`text-right px-3 font-semibold ${accColor}`}>
                            {acc != null ? `${(acc * 100).toFixed(0)}%` : "—"}
                          </td>
                          <td className={`text-right px-3 ${dominant === "up" ? "text-green-400 font-semibold" : "text-gray-600"}`}>
                            {v.up}
                          </td>
                          <td className={`text-right px-3 ${dominant === "neutral" ? "text-yellow-400 font-semibold" : "text-gray-600"}`}>
                            {v.neutral}
                          </td>
                          <td className={`text-right px-3 ${dominant === "down" ? "text-red-400 font-semibold" : "text-gray-600"}`}>
                            {v.down}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
