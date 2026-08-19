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

// ── Confusion matrix helper ─────────────────────────────────────────────────
type Matrix = Record<string, Record<string, number>>;

function buildConfusionMatrix(data: HistoryPoint[]): Matrix {
  const dirs = ["up", "neutral", "down"];
  const m: Matrix = {};
  dirs.forEach(r => { m[r] = {}; dirs.forEach(p => { m[r][p] = 0; }); });
  data.forEach(d => {
    const r = d.realized_direction;
    const p = d.predicted_direction;
    if (m[r] && m[r][p] !== undefined) m[r][p]++;
  });
  return m;
}

function ConfusionMatrix({ data }: { data: HistoryPoint[] }) {
  const matrix = buildConfusionMatrix(data);
  const dirs = ["up", "neutral", "down"];
  const total = data.length || 1;

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-5">
      <h2 className="text-sm font-semibold text-gray-300 mb-1">Confusion matrix</h2>
      <p className="text-xs text-gray-600 mb-4">řádky = realizované, sloupce = predikované</p>
      <table className="w-full text-xs text-center">
        <thead>
          <tr className="text-gray-500">
            <th className="py-1 pr-2 text-left text-gray-600">real ↓ / pred →</th>
            {dirs.map(d => (
              <th key={d} className="py-1 px-3 font-semibold" style={{ color: DIR_COLORS[d] }}>
                {d.toUpperCase()}
              </th>
            ))}
            <th className="py-1 px-3 text-gray-500">Σ</th>
          </tr>
        </thead>
        <tbody>
          {dirs.map(real => {
            const rowTotal = dirs.reduce((s, p) => s + matrix[real][p], 0);
            return (
              <tr key={real} className="border-t border-[#2a2d3a]/40">
                <td className="py-2 pr-2 text-left font-semibold" style={{ color: DIR_COLORS[real] }}>
                  {real.toUpperCase()}
                </td>
                {dirs.map(pred => {
                  const count = matrix[real][pred];
                  const isCorrect = real === pred;
                  const intensity = total > 0 ? count / total : 0;
                  const bg = isCorrect
                    ? `rgba(34,197,94,${Math.min(intensity * 3, 0.4)})`
                    : count > 0 ? `rgba(239,68,68,${Math.min(intensity * 3, 0.35)})` : "transparent";
                  return (
                    <td key={pred} className="py-2 px-3 rounded"
                        style={{ backgroundColor: bg }}>
                      <span className={count > 0 ? (isCorrect ? "text-green-400 font-bold" : "text-red-400 font-semibold") : "text-gray-700"}>
                        {count}
                      </span>
                    </td>
                  );
                })}
                <td className="py-2 px-3 text-gray-500">{rowTotal}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Multi-ticker overview ───────────────────────────────────────────────────
function MultiTickerBar({ days }: { days: number }) {
  const [tickerStats, setTickerStats] = useState<Record<string, AccuracyStats | null>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled(TICKERS.map(t => api.getStats(t, days))).then(results => {
      const map: Record<string, AccuracyStats | null> = {};
      TICKERS.forEach((t, i) => {
        map[t] = results[i].status === "fulfilled" ? results[i].value : null;
      });
      setTickerStats(map);
      setLoading(false);
    });
  }, [days]);

  if (loading) return <div className="h-24 rounded-xl bg-[#1a1d27] animate-pulse border border-[#2a2d3a]" />;

  const bars = TICKERS
    .map(t => ({
      ticker: t,
      accuracy: tickerStats[t]?.accuracy ?? null,
      total: tickerStats[t]?.total ?? 0,
    }))
    .filter(b => b.total > 0);

  if (bars.length === 0) return null;

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-5">
      <h2 className="text-sm font-semibold text-gray-300 mb-4">Přesnost podle tickeru</h2>
      <div className="space-y-3">
        {bars.map(({ ticker, accuracy, total }) => {
          const pct = accuracy != null ? accuracy * 100 : 0;
          const color = pct >= 60 ? "#22c55e" : pct >= 45 ? "#eab308" : "#ef4444";
          return (
            <div key={ticker} className="flex items-center gap-3">
              <span className="w-16 text-xs font-mono text-gray-300 shrink-0">{ticker}</span>
              <div className="flex-1 bg-[#0d0f17] rounded-full h-4 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{ width: `${pct}%`, backgroundColor: color + "99", border: `1px solid ${color}` }}
                />
              </div>
              <span className="w-20 text-xs text-right shrink-0" style={{ color }}>
                {accuracy != null ? `${pct.toFixed(0)}%` : "—"}
                <span className="text-gray-600 ml-1">({total})</span>
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-gray-600 mt-3">Přesnost = predikovaný směr == realizovaný (15min okno)</p>
    </div>
  );
}

// ── Bias analysis ───────────────────────────────────────────────────────────
function BiasAnalysis({ data }: { data: HistoryPoint[] }) {
  if (data.length === 0) return null;

  const pred = { up: 0, neutral: 0, down: 0 };
  const real = { up: 0, neutral: 0, down: 0 };
  data.forEach(d => {
    pred[d.predicted_direction as keyof typeof pred]++;
    real[d.realized_direction as keyof typeof real]++;
  });

  const total = data.length;
  const dirs = [
    { key: "up",      label: "↑ UP",   color: "#22c55e" },
    { key: "neutral", label: "→ NEUT", color: "#eab308" },
    { key: "down",    label: "↓ DOWN", color: "#ef4444" },
  ] as const;

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-5">
      <h2 className="text-sm font-semibold text-gray-300 mb-4">Bias analýza — predikce vs. realita</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-[#2a2d3a]">
              <th className="text-left py-2 pr-4">Směr</th>
              <th className="text-right py-2 px-3">Predikováno</th>
              <th className="text-right py-2 px-3">Realizováno</th>
              <th className="text-right py-2 px-3">Rozdíl</th>
              <th className="py-2 px-3 text-left">Vizualizace</th>
            </tr>
          </thead>
          <tbody>
            {dirs.map(({ key, label, color }) => {
              const p = pred[key];
              const r = real[key];
              const diff = p - r;
              const pPct = total > 0 ? (p / total) * 100 : 0;
              const rPct = total > 0 ? (r / total) * 100 : 0;
              return (
                <tr key={key} className="border-b border-[#2a2d3a]/40">
                  <td className="py-2 pr-4 font-semibold" style={{ color }}>{label}</td>
                  <td className="text-right px-3 text-gray-300">{p} <span className="text-gray-600">({pPct.toFixed(0)}%)</span></td>
                  <td className="text-right px-3 text-gray-300">{r} <span className="text-gray-600">({rPct.toFixed(0)}%)</span></td>
                  <td className={`text-right px-3 font-semibold ${diff > 0 ? "text-orange-400" : diff < 0 ? "text-blue-400" : "text-gray-600"}`}>
                    {diff > 0 ? `+${diff}` : diff}
                  </td>
                  <td className="py-2 px-3">
                    <div className="relative h-3 w-40 bg-[#0d0f17] rounded">
                      <div className="absolute top-0 left-0 h-full rounded opacity-40" style={{ width: `${rPct}%`, backgroundColor: color }} />
                      <div className="absolute top-0 left-0 h-full rounded border" style={{ width: `${pPct}%`, borderColor: color }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="text-[10px] text-gray-600 mt-2">
          Plná čára = predikce, výplň = realita. Kladný rozdíl = model over-predikuje tento směr.
        </p>
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────
export default function HistoryPage() {
  const [data, setData] = useState<HistoryPoint[]>([]);
  const [stats, setStats] = useState<AccuracyStats | null>(null);
  const [ticker, setTicker] = useState("ES");
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

  const totalAcc = stats?.accuracy;
  const accColor = totalAcc == null ? "text-gray-500"
    : totalAcc >= 0.6 ? "text-green-400"
    : totalAcc >= 0.45 ? "text-yellow-400"
    : "text-red-400";

  return (
    <div className="space-y-6">
      {/* Header */}
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

      {/* Multi-ticker overview */}
      <MultiTickerBar days={days} />

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          {
            label: "Vzorků s reakcí",
            value: stats?.total ?? data.length,
            sub: `${ticker} / ${days}d`,
          },
          {
            label: "Správných",
            value: stats?.correct ?? data.filter((d) => d.accuracy).length,
          },
          {
            label: "Přesnost",
            value: totalAcc != null
              ? <span className={accColor}>{(totalAcc * 100).toFixed(1)}%</span>
              : data.length > 0
              ? <span className={accColor}>{accuracy.toFixed(1)}%</span>
              : "—",
          },
          {
            label: "Kategorií (≥2)",
            value: catRows.length,
          },
        ].map(({ label, value, sub }) => (
          <div key={label} className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4 text-center">
            <div className="text-2xl font-bold text-white">{value}</div>
            {sub && <div className="text-[10px] text-gray-600 mt-0.5">{sub}</div>}
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
          Žádná historická data. Spusť <code className="text-orange-400">/api/calibrate</code> pro záznam tržních reakcí (min. 15 min po vydání zprávy).
        </div>
      ) : (
        <>
          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Accuracy over time */}
            <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-5">
              <h2 className="text-sm font-semibold text-gray-300 mb-4">Přesnost v čase (posl. 30 dní)</h2>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={byDate}>
                  <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#6b7280" }} tickLine={false}
                    tickFormatter={(v) => v.slice(5)} />
                  <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 10, fill: "#6b7280" }} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8 }}
                    formatter={(v: number) => [`${v.toFixed(0)}%`, "Přesnost"]}
                    labelFormatter={(l) => `Datum: ${l}`}
                  />
                  <Bar dataKey="accuracy" radius={[4, 4, 0, 0]}>
                    {byDate.map((entry, i) => (
                      <Cell key={i} fill={entry.accuracy >= 60 ? "#22c55e" : entry.accuracy >= 40 ? "#eab308" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Realized direction distribution */}
            <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-5">
              <h2 className="text-sm font-semibold text-gray-300 mb-4">Realizované směry — {ticker}</h2>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={dirDist.filter(d => d.value > 0)}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={75}
                    label={({ name, percent, value }) =>
                      percent > 0.04 ? `${name} ${value} (${(percent * 100).toFixed(0)}%)` : ""
                    }
                    labelLine={false}
                  >
                    {dirDist.filter(d => d.value > 0).map((entry) => (
                      <Cell key={entry.name} fill={entry.fill + "bb"} stroke={entry.fill} strokeWidth={1} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Confusion matrix + bias */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ConfusionMatrix data={data} />
            <BiasAnalysis data={data} />
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
                      const barW = Math.min((v.total / (catRows[0][1].total || 1)) * 100, 100);
                      return (
                        <tr key={cat} className="border-b border-[#2a2d3a]/40 hover:bg-white/[0.02]">
                          <td className="py-2 pr-2">
                            <div className="flex items-center gap-2">
                              <div className="w-16 h-1 bg-[#0d0f17] rounded overflow-hidden shrink-0">
                                <div className="h-full bg-blue-600 rounded" style={{ width: `${barW}%` }} />
                              </div>
                              <span className="text-gray-300 font-mono">{cat}</span>
                            </div>
                          </td>
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
