"use client";

import { useEffect, useState } from "react";
import { Sunrise, Info, X } from "lucide-react";

/* ---------------------------------------------------------------- typy */

interface OrbAgg {
  days: number; both: number; high_only: number; low_only: number; neither: number;
  high_taken: number; low_taken: number; break_rate: number; one_sided: number;
  order: { high_to_low: number; low_to_high: number };
}
interface OrbRollPoint {
  from: string; to: string; n: number;
  high_taken: number; low_taken: number; break_rate: number;
  one_sided: number; both: number; neither: number;
}
interface OrbSession {
  open_utc: number; or_range_avg: number;
  overall: Record<string, OrbAgg>;
  rolling: Record<string, OrbRollPoint[]>;
}
interface OrbSessions {
  _meta: {
    months: number; window_days: number; step_days: number; from: string; to: string;
    horizons: Record<string, string>; or_lengths: Record<string, string>;
  };
  or5: Record<string, OrbSession>;
  or15: Record<string, OrbSession>;
}
interface OrbData {
  meta: { instrument: string; label: string; unit: string; from: string; to: string };
  orb_sessions?: OrbSessions;
}

/* ------------------------------------------------------------ pomocné */

type LabelList = [string, string][];
const SESSION_LABELS: LabelList = [["asia", "Asia"], ["london", "London"], ["ny", "NY"]];
const SIDES_LABELS: LabelList = [
  ["both", "Obě strany"], ["high_only", "Pouze high"], ["low_only", "Pouze low"], ["neither", "Ani jedna"],
];

type MetricKey = "one_sided" | "both" | "neither" | "high_taken" | "low_taken";
// pol: +1 = růst zlepšuje edge, -1 = růst zhoršuje (whipsaw), 0 = neutrální (jen roste/klesá)
const METRICS: Record<MetricKey, { label: string; short: string; pol: number; color: string }> = {
  one_sided: { label: "1-sided proraz (čistý směr)", short: "1-sided", pol: 1, color: "#3b82f6" },
  both: { label: "Obě strany (whipsaw)", short: "Obě strany", pol: -1, color: "#f59e0b" },
  neither: { label: "Ani jedna (range drží)", short: "Ani jedna", pol: 0, color: "#a855f7" },
  high_taken: { label: "High vybráno", short: "High", pol: 0, color: "#4ade80" },
  low_taken: { label: "Low vybráno", short: "Low", pol: 0, color: "#f87171" },
};
const METRIC_ORDER: MetricKey[] = ["one_sided", "both", "neither", "high_taken", "low_taken"];

function Delta({ now, prev }: { now: number; prev?: number }) {
  if (prev === undefined || prev === null) return null;
  const d = Math.round((now - prev) * 10) / 10;
  if (Math.abs(d) < 0.1) return null;
  const color = d > 0 ? "#4ade80" : "#f87171";
  return (
    <span className="text-[10px] font-medium ml-1" style={{ color }} title={`Minulý měsíc: ${prev.toFixed(1)} %`}>
      {d > 0 ? "▲" : "▼"}{Math.abs(d).toFixed(1)}
    </span>
  );
}

function Bar({ label, value, prev, accent = "#3b82f6" }: {
  label: string; value: number; prev?: number; accent?: string;
}) {
  const width = Math.max(2, value);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 shrink-0 text-gray-400 truncate">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-[#232735] overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${width}%`, background: accent }} />
      </div>
      <span className="w-20 text-right font-medium whitespace-nowrap" style={{ color: value >= 50 ? accent : "#9ca3af" }}>
        {value.toFixed(1)} %<Delta now={value} prev={prev} />
      </span>
    </div>
  );
}

function BarGroup({ data, prevData, labels }: {
  data: Record<string, number>; prevData?: Record<string, number>; labels: LabelList;
}) {
  return (
    <div className="space-y-2">
      {labels.filter(([k]) => typeof data[k] === "number").map(([k, label]) => (
        <Bar key={k} label={label} value={data[k]} prev={typeof prevData?.[k] === "number" ? prevData[k] : undefined} />
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- ORB */

function fitLine(ys: number[]): { a: number; b: number } {
  const n = ys.length;
  if (n < 2) return { a: ys[0] ?? 0, b: 0 };
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  ys.forEach((y, x) => { sx += x; sy += y; sxx += x * x; sxy += x * y; });
  const d = n * sxx - sx * sx || 1;
  const b = (n * sxy - sx * sy) / d;
  return { a: (sy - b * sx) / n, b };
}

function OrbSparkline({ points, color }: { points: number[]; color: string }) {
  const W = 260, H = 62, pT = 6, pB = 6, pL = 2, pR = 2;
  if (points.length < 2) return null;
  const iw = W - pL - pR, ih = H - pT - pB;
  const X = (i: number) => pL + (iw * i) / (points.length - 1);
  const Y = (v: number) => pT + ih * (1 - v / 100);
  const line = points.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1)).join(" ");
  const area = `${line} L ${X(points.length - 1).toFixed(1)} ${Y(0)} L ${X(0).toFixed(1)} ${Y(0)} Z`;
  const f = fitLine(points);
  const tr = `M ${X(0).toFixed(1)} ${Y(f.a).toFixed(1)} L ${X(points.length - 1).toFixed(1)} ${Y(f.a + f.b * (points.length - 1)).toFixed(1)}`;
  const uid = "orb" + Math.round(Math.random() * 1e6);
  const lx = X(points.length - 1), ly = Y(points[points.length - 1]);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 62 }} preserveAspectRatio="none">
      <defs>
        <linearGradient id={uid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.22" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 50, 100].map((g) => (
        <line key={g} x1={pL} y1={Y(g)} x2={W - pR} y2={Y(g)} stroke="#232735" strokeWidth="1" />
      ))}
      <path d={area} fill={`url(#${uid})`} />
      <path d={tr} stroke="#64748b" strokeWidth="1.2" strokeDasharray="4 4" fill="none" />
      <path d={line} stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx} cy={ly} r="3" fill={color} stroke="#151823" strokeWidth="1.4" />
    </svg>
  );
}

function orbVerdict(points: number[], pol: number): { txt: string; color: string; arrow: string; delta: number } {
  const f = fitLine(points);
  const delta = f.b * (points.length - 1); // fitnutá změna metriky start→konec za 6M
  if (Math.abs(delta) < 4) return { txt: "Stabilní", color: "#eab308", arrow: "→", delta };
  const up = delta > 0;
  if (pol === 0) return { txt: up ? "Roste" : "Klesá", color: "#93a4c4", arrow: up ? "▲" : "▼", delta };
  const good = delta * pol > 0;
  return { txt: good ? "Zpevňuje" : "Rozpadá se", color: good ? "#4ade80" : "#f87171", arrow: up ? "▲" : "▼", delta };
}

function OrbCard({ name, sess, hor, metric }: {
  name: string; sess: OrbSession; hor: string; metric: MetricKey;
}) {
  const ov = sess.overall[hor];
  const roll = sess.rolling[hor];
  const M = METRICS[metric];
  const open = String(sess.open_utc).padStart(2, "0") + ":00";
  const os = roll ? roll.map((r) => r[metric]) : [];
  const v = roll && os.length > 1 ? orbVerdict(os, M.pol) : null;
  const cur = roll && os.length ? os[os.length - 1] : (ov as unknown as Record<string, number>)[metric];
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-white">{name}</h3>
          <p className="text-[10px] uppercase tracking-wider text-gray-500 mt-0.5">
            open {open} UTC · {ov.days} dní · OR-avg {sess.or_range_avg}
          </p>
        </div>
        {v && (
          <span className="text-[10px] font-semibold px-2 py-1 rounded-full whitespace-nowrap"
            style={{ color: v.color, background: v.color + "1a" }}>
            {v.arrow} {v.txt}
          </span>
        )}
      </div>

      {roll && (
        <div className="mt-2 mb-1">
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-bold text-white">{cur}</span>
            <span className="text-[11px] text-gray-500">% · {M.label}</span>
            {v && (
              <span className="text-[10px] ml-auto font-medium" style={{ color: v.color }}>
                {v.delta >= 0 ? "+" : ""}{v.delta.toFixed(1)} pp / 6M
              </span>
            )}
          </div>
          <OrbSparkline points={os} color={M.color} />
        </div>
      )}

      <div className="mt-2">
        <BarGroup data={ov as unknown as Record<string, number>} labels={SIDES_LABELS} />
      </div>

      <div className="mt-3 pt-3 border-t border-[#232735] space-y-2">
        <Bar label="High vybráno" value={ov.high_taken} accent="#3b82f6" />
        <Bar label="Low vybráno" value={ov.low_taken} accent="#3b82f6" />
      </div>

      <div className="mt-3 pt-3 border-t border-[#232735] space-y-2">
        <Bar label="Nejdřív High" value={ov.order?.high_to_low ?? 0} accent="#64748b" />
        <Bar label="Nejdřív Low" value={ov.order?.low_to_high ?? 0} accent="#64748b" />
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- info modal */

function InfoModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div className="bg-[#12141c] border border-[#2a2d3a] rounded-2xl max-w-2xl w-full p-6 my-8" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Jak číst ORB</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
        </div>
        <div className="space-y-3 text-sm text-gray-300">
          <p><b className="text-white">Opening range (OR)</b> = prvních 5 nebo 15 min po openu session (1 nebo 3 pětiminutové svíčky). Sledujeme, jak často se ve zvoleném horizontu <b className="text-white">vybere high / low</b> tohoto rangu.</p>
          <p><b className="text-blue-400">1-sided proraz</b> = vybere se jen jedna strana (čistý směr). <b className="text-blue-400">Obě strany</b> = vybere se high i low (whipsaw). <b className="text-blue-400">Ani jedna</b> = range drží.</p>
          <p><b className="text-white">Horizont</b>: 30 / 60 min po OR, nebo celá session (na celé session se OR sundá skoro vždy — edge je čitelný na 30/60 min).</p>
          <p><b className="text-white">Trend (křivka)</b> = vyber, kterou metriku sleduje velké číslo, sparkline a verdikt: 1-sided, Obě strany, Ani jedna, High nebo Low. Bary pod tím ukazují celé rozdělení vždy.</p>
          <p><b className="text-white">Verdikt</b> = lineární regrese zvolené metriky přes plovoucí 30denní okna za 6 měsíců. U „1-sided" a „Obě strany" hodnotí edge (Zpevňuje / Rozpadá se), u ostatních jen směr (Roste / Klesá). Sparkline ukazuje ten trend.</p>
          <p><b className="text-white">Nejdřív High / Low</b> = která strana OR padne první.</p>
          <p className="text-xs text-gray-500">Open = start session (Asia dle instrumentu, London 07:00, NY 12:00 UTC — session open, ne cash open 13:30). Data: Dukascopy 5m bary. Statistika popisuje strukturu trhu, není investiční doporučení.</p>
        </div>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- page */

export default function OrbPage() {
  const [data, setData] = useState<Record<string, OrbData>>({});
  const [selected, setSelected] = useState<string>("nq");
  const [error, setError] = useState<string | null>(null);
  const [orLen, setOrLen] = useState<"or5" | "or15">("or5");
  const [hor, setHor] = useState<"m30" | "m60" | "sess">("m60");
  const [metric, setMetric] = useState<MetricKey>("one_sided");
  const [showInfo, setShowInfo] = useState(false);

  useEffect(() => {
    Promise.allSettled(
      ["nq", "gold", "ym"].map((k) =>
        fetch(`/stats/${k}.json`, { cache: "no-store" }).then((r) => {
          if (!r.ok) throw new Error(`${k}: ${r.status}`);
          return r.json().then((j: OrbData) => [k, j] as const);
        })
      )
    ).then((results) => {
      const ok = Object.fromEntries(
        results
          .filter((r): r is PromiseFulfilledResult<readonly [string, OrbData]> => r.status === "fulfilled")
          .map((r) => r.value)
      );
      if (Object.keys(ok).length === 0) setError("ORB statistiky nejsou k dispozici. Spusť data/compute_stats.py.");
      setData(ok);
    });
  }, []);

  const stats = data[selected];
  const orb = stats?.orb_sessions;

  return (
    <div className="space-y-8">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-950/60 border border-blue-900/50">
              <Sunrise size={16} className="text-blue-400" />
            </span>
            <h1 className="text-2xl font-bold text-white">Opening Range Breakout</h1>
          </div>
          <button
            onClick={() => setShowInfo(true)}
            className="flex items-center gap-1.5 rounded-full border border-blue-800 bg-blue-950/40 px-3 py-1 text-xs text-blue-300 hover:bg-blue-900/40 transition-colors"
          >
            <Info size={13} /> Jak číst
          </button>
        </div>
        <p className="text-sm text-gray-400 mt-1">
          Vybrání high/low opening range po openu Asia / London / NY — a jestli se edge za 6 měsíců zpevňuje, nebo rozpadá
        </p>
      </div>

      {/* Filtr instrumentu */}
      <div className="flex flex-wrap items-center gap-2 -mt-4">
        {(["nq", "gold", "ym"] as const).map((k) => (
          <button
            key={k}
            onClick={() => setSelected(k)}
            disabled={!data[k]}
            className={`rounded-lg px-4 py-2 text-sm font-medium border transition-colors disabled:opacity-40 ${
              selected === k
                ? "bg-[#1e2536] text-white border-[#2f3b55]"
                : "bg-[#151823] text-gray-400 border-[#2a2d3a] hover:text-white"
            }`}
          >
            {k === "nq" ? "NQ" : k === "gold" ? "GOLD" : "YM"}
          </button>
        ))}
        {orb && (
          <span className="ml-2 text-xs text-gray-500">
            plovoucí okno {orb._meta.window_days} dní · krok {orb._meta.step_days} · {orb._meta.from} → {orb._meta.to}
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">{error}</div>
      )}

      {!stats && !error && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-72 rounded-2xl bg-[#151823] animate-pulse border border-[#2a2d3a]" />
          ))}
        </div>
      )}

      {stats && !orb && !error && (
        <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">
          Tento instrument zatím nemá ORB data — přegeneruj statistiky (data/compute_stats.py).
        </div>
      )}

      {orb && (
        <>
          {/* Filtry ORB */}
          <div className="flex flex-wrap gap-x-6 gap-y-3">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider text-gray-500 mr-1">ORB délka</span>
              {(["or5", "or15"] as const).map((k) => (
                <button key={k} onClick={() => setOrLen(k)}
                  className={`rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
                    orLen === k ? "bg-[#1e2536] text-white border-[#2f3b55]"
                      : "bg-[#151823] text-gray-400 border-[#2a2d3a] hover:text-white"}`}>
                  {k === "or5" ? "5 min" : "15 min"}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider text-gray-500 mr-1">Horizont</span>
              {(["m30", "m60", "sess"] as const).map((k) => (
                <button key={k} onClick={() => setHor(k)}
                  className={`rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
                    hor === k ? "bg-[#1e2536] text-white border-[#2f3b55]"
                      : "bg-[#151823] text-gray-400 border-[#2a2d3a] hover:text-white"}`}>
                  {k === "m30" ? "30 min" : k === "m60" ? "60 min" : "session"}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider text-gray-500 mr-1">Trend (křivka)</span>
              {METRIC_ORDER.map((k) => (
                <button key={k} onClick={() => setMetric(k)}
                  className={`rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
                    metric === k ? "bg-[#1e2536] text-white border-[#2f3b55]"
                      : "bg-[#151823] text-gray-400 border-[#2a2d3a] hover:text-white"}`}>
                  {METRICS[k].short}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {SESSION_LABELS.map(([k, name]) => {
              const sess = orb[orLen][k];
              if (!sess) return null;
              return <OrbCard key={k} name={name} sess={sess} hor={hor} metric={metric} />;
            })}
          </div>

          {hor === "sess" && (
            <p className="text-[11px] text-gray-600">
              Na celé session se OR sundá skoro vždy (~100 %) — směrový edge je čitelný na 30/60min horizontu.
            </p>
          )}
        </>
      )}

      {showInfo && <InfoModal onClose={() => setShowInfo(false)} />}
    </div>
  );
}
