"use client";

import { useMemo } from "react";
import { useSeasonality } from "./data";
import { Card } from "./ui";

// Barvy let jako na běžných grafech sezónnosti: letos modrá (silná), loni zelená, předloni oranžová.
const YEAR_COLORS = ["#f59e0b", "#22c55e", "#3b82f6"];
const MONTH_TICKS: [number, string][] = [[0, "led"], [120, "kvě"], [243, "zář"]];
const W = 360, H = 150, PAD = { l: 2, r: 36, t: 8, b: 18 };

type Pts = [number, number][];
export interface SeasonAsset { symbol: string; label: string; name?: string | null }

const pct = (v: number, digits = 1) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toLocaleString("cs-CZ", { maximumFractionDigits: digits })} %`;
const dayOfYear = (d = new Date()) => Math.floor((Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) - Date.UTC(d.getFullYear(), 0, 1)) / 86_400_000);

/** Změna od dnešního dne v roce do konce roku (pro minulé roky) — „co obvykle přichází". */
function restOfYear(pts: Pts, today: number): number | null {
  const before = pts.filter(([d]) => d <= today);
  if (!before.length || pts[pts.length - 1][0] < 330) return null;
  const v0 = before[before.length - 1][1], v1 = pts[pts.length - 1][1];
  return ((1 + v1 / 100) / (1 + v0 / 100) - 1) * 100;
}

function SeasonChart({ years, curves }: { years: number[]; curves: Record<string, Pts> }) {
  const all = years.flatMap((y) => curves[String(y)] ?? []);
  const lo = Math.min(0, ...all.map((p) => p[1])), hi = Math.max(0, ...all.map((p) => p[1]));
  const span = Math.max(hi - lo, 2), y0 = lo - span * 0.08, y1 = hi + span * 0.08;
  const x = (d: number) => PAD.l + (d / 365) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const today = dayOfYear();
  const ticks = [hi, 0, lo].filter((v, i, a) => a.indexOf(v) === i && (v === 0 || Math.abs(v) >= span * 0.15));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Sezónnost — vývoj ceny během roku">
      {MONTH_TICKS.map(([d, m]) => (
        <g key={m}>
          {d > 0 && <line x1={x(d)} x2={x(d)} y1={PAD.t} y2={H - PAD.b} stroke="currentColor" strokeDasharray="3 4" className="text-gray-600" strokeWidth={0.8} />}
          <text x={x(d) + (d ? 0 : 1)} y={H - 4} textAnchor={d ? "middle" : "start"} fontSize={10} className="fill-gray-500">{m}</text>
        </g>
      ))}
      <line x1={x(today)} x2={x(today)} y1={PAD.t} y2={H - PAD.b} stroke="currentColor" className="text-gray-400" strokeWidth={0.8} opacity={0.6} />
      <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} stroke="currentColor" className="text-gray-400" strokeWidth={0.8} />
      {ticks.map((v) => (
        <text key={v} x={W - PAD.r + 4} y={y(v) + 3} fontSize={10} className="fill-gray-500">{v === 0 ? "0 %" : pct(v, 0)}</text>
      ))}
      {years.map((yr, i) => {
        const p = curves[String(yr)];
        if (!p?.length) return null;
        const last = i === years.length - 1;
        return (
          <polyline key={yr} fill="none" stroke={YEAR_COLORS[i % YEAR_COLORS.length]} strokeWidth={last ? 2.4 : 1.4}
            strokeLinejoin="round" opacity={last ? 1 : 0.85} points={p.map(([d, v]) => `${x(d).toFixed(1)},${y(v).toFixed(1)}`).join(" ")} />
        );
      })}
    </svg>
  );
}

function SeasonCard({ asset, years, curves }: { asset: SeasonAsset; years: number[]; curves: Record<string, Pts> }) {
  return (
    <div className="rounded-xl border border-line bg-sunken p-3.5">
      <div className="flex items-baseline gap-2">
        <span className="font-semibold text-white">{asset.label}</span>
        {asset.name && <span className="truncate text-[11.5px] text-gray-500">{asset.name}</span>}
      </div>
      <SeasonBody years={years} curves={curves} />
    </div>
  );
}

/** Graf + legenda let + „od dnešního data do konce roku". */
function SeasonBody({ years, curves }: { years: number[]; curves: Record<string, Pts> }) {
  const has = years.filter((y) => curves[String(y)]?.length);
  const today = dayOfYear();
  const ahead = years.slice(0, -1).map((y) => [y, curves[String(y)] ? restOfYear(curves[String(y)], today) : null] as const)
    .filter(([, v]) => v != null) as [number, number][];
  return (
    <>
      {has.length === 0 ? (
        <p className="mt-2 text-[12.5px] text-gray-500">Historii cen tohoto titulu zatím nemáme.</p>
      ) : (
        <>
          <div className="mt-1.5"><SeasonChart years={years} curves={curves} /></div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] text-gray-400">
            {years.map((yr, i) => {
              const p = curves[String(yr)];
              if (!p?.length) return null;
              return (
                <span key={yr} className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ background: YEAR_COLORS[i % YEAR_COLORS.length] }} />
                  {yr} <b className="text-gray-300">{pct(p[p.length - 1][1])}</b>
                </span>
              );
            })}
          </div>
          {ahead.length > 0 && (
            <p className="mt-1.5 text-[12px] text-gray-400">
              Od dnešního data do konce roku: {ahead.map(([y, v]) => `${y} ${pct(v)}`).join(", ")}.
            </p>
          )}
        </>
      )}
    </>
  );
}

/** Sezónnost jednoho titulu (Pokročilý: Dashboard, detail firmy ve Valuation Radaru). Bez dat se skryje. */
export function SeasonPanel({ symbol, label, className = "" }: { symbol: string; label: string; className?: string }) {
  const { data, error } = useSeasonality([symbol]);
  const curves = (data?.items[0]?.years ?? {}) as Record<string, Pts>;
  if (error || (data && Object.keys(curves).length === 0)) return null;
  return (
    <div className={className}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h3 className="text-sm font-semibold text-white">Sezónnost · {label}</h3>
        <span className="text-[11px] text-gray-500">poslední 3 roky · % od začátku ledna · svislá čára = dnes</span>
      </div>
      <div className="max-w-2xl">
        {!data ? <div className="mt-2 h-40 animate-pulse rounded-lg bg-raised" /> : <SeasonBody years={data.years} curves={curves} />}
      </div>
    </div>
  );
}

/** Sezónnost posledních 3 let pro aktiva z Přehledu (stejný typ grafu jako „Seasonals" u brokerů). */
export function SeasonalitySection({ assets }: { assets: SeasonAsset[] }) {
  const list = useMemo(() => assets.filter((a, i) => assets.findIndex((b) => b.symbol === a.symbol) === i), [assets]);
  const { data, error } = useSeasonality(list.map((a) => a.symbol));
  if (!list.length || error) return null;
  return (
    <Card>
      <h2 className="text-[15px] font-bold text-white">Sezónnost: jak se jim dařilo během roku</h2>
      <p className="mb-3 text-[12.5px] text-gray-500">
        Každá čára je jeden rok — o kolik % byla cena výš nebo níž než na začátku ledna. Svislá čára = dnešek.
        Pomáhá vidět, jestli bývá konec roku klidný, nebo rozkolísaný. Minulé roky ale nejsou předpověď.
      </p>
      {!data ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{list.map((a) => <div key={a.symbol} className="h-52 animate-pulse rounded-xl bg-sunken" />)}</div>
      ) : (() => {
        const curvesOf = (a: SeasonAsset) => (data.items.find((i) => i.symbol === a.symbol.toUpperCase())?.years ?? {}) as Record<string, Pts>;
        const withData = list.filter((a) => Object.keys(curvesOf(a)).length > 0);
        const missing = list.filter((a) => !withData.includes(a));
        return (
          <>
            {withData.length > 0 && (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {withData.map((a) => <SeasonCard key={a.symbol} asset={a} years={data.years} curves={curvesOf(a)} />)}
              </div>
            )}
            {missing.length > 0 && (
              <p className="mt-2 text-[12px] text-gray-500">Pro {missing.map((a) => a.label).join(", ")} zatím historii cen nemáme.</p>
            )}
          </>
        );
      })()}
    </Card>
  );
}
