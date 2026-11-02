"use client";

// „Dnešní den v číslech“ — dnešní NQ / YM / GOLD vůči historii (Spark data/edge_live.py každé
// 2 min → /api/marketstats/live/<key>, plán Trader+). Bez plánu se karta neukáže.

import { useCallback, useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";
import { authHeaders } from "@/lib/auth";
import { type P, Prob, clock, cz } from "@/components/stats/prob";

const KEY: Record<string, string> = { NQ: "nq", YM: "ym", XAUUSD: "gold", GOLD: "gold" };
const PHASE: Record<string, string> = { pre: "před otevřením RTH", rth: "RTH běží", post: "RTH skončila" };
const CAT: Record<string, [string, string]> = {
  normal: ["běžný den", "#9ca3af"], above: ["nadprůměrný den", "#eab308"], extreme: ["extrémní den", "#f97316"],
};
const SCEN: Record<string, string> = {
  both: "London vzal obě strany Asie", inside: "London zůstal uvnitř Asie",
  high_only: "London vzal jen Asia high", low_only: "London vzal jen Asia low",
};
const EVENT: Record<string, string> = { fomc: "FOMC", cpi: "CPI", nfp: "NFP", ppi: "PPI" };

interface Live {
  meta: { instrument: string; updated: string; src: string; stats_from?: string; stats_to?: string; days?: number; rth_et?: [number, number]; unit?: string };
  date: string; now_et: string; phase: "pre" | "rth" | "post"; price: number | null; typical_range_pts: number | null; events: string[];
  range?: {
    so_far_pts: number; vs_typical: number; t_high: number; t_low: number; high: number; low: number;
    checkpoint?: number; percentile?: number; remaining_pts?: Record<"p25" | "p50" | "p75" | "p90", number>; remaining_n?: number;
    category?: string; final_percentile?: number;
  };
  extremes?: { hi_age: number; lo_age: number; high_holds: P; low_holds: P; both_hold: P };
  trend?: { der: number; close_location: number | null; direction: string; p_trend_day?: P; p_continues?: P };
  sessions?: {
    asia_high?: number; asia_low?: number; pre?: string; pre_stat?: P; scenario?: string;
    scenario_stat?: { n: number; ny_london_high: P; ny_london_low: P };
    ny_took_london_high?: boolean; ny_took_london_low?: boolean; conditional?: P & { text: string };
  };
  macro: { event: string; n: number; rth?: { p50?: number }; rth_ci?: [number, number] | null; window?: string; win?: { p50?: number } }[];
}

const n0 = (v?: number | null) => (v == null ? "—" : Math.round(v).toLocaleString("cs-CZ"));

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-t border-[#232735] py-2 sm:grid-cols-[120px,1fr]">
      <div className="text-[11px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-[12px] leading-relaxed text-gray-300">{children}</div>
    </div>
  );
}

export function DayLiveCard({ ticker }: { ticker: string }) {
  const key = KEY[ticker.toUpperCase()];
  const [d, setD] = useState<Live | null>(null);
  const load = useCallback(() => {
    if (!key) return;
    fetch(`/api/marketstats/live/${key}`, { cache: "no-store", headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null)).then(setD).catch(() => {});
  }, [key]);
  useEffect(() => { setD(null); load(); }, [load]);
  useEffect(() => {
    const id = setInterval(() => { if (document.visibilityState === "visible") load(); }, 120_000);
    return () => clearInterval(id);
  }, [load]);

  if (!key || !d) return null;
  const unit = d.meta.unit ?? "bodů";
  const open = d.meta.rth_et?.[0] ?? 9.5;
  const r = d.range, ex = d.extremes, tr = d.trend, ss = d.sessions;
  const stale = Date.now() - new Date(d.meta.updated).getTime() > 20 * 60_000 && d.phase !== "post";
  // Kategorie = vůči CELÝM dnům → během RTH jen když už je den nad normálem („už teď nadprůměrný“)
  const cat = r?.category && (d.phase === "post" || r.category !== "normal") ? CAT[r.category] : null;
  const bar = r ? Math.min(100, (r.vs_typical / 2.5) * 100) : 0;

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <BarChart3 size={15} className="text-blue-400" />
        <h2 className="text-sm font-semibold text-white">Dnešní den v číslech · {d.meta.instrument}</h2>
        <span className="text-[10px] text-gray-500">{PHASE[d.phase]} · {d.now_et} ET{stale ? " · data se neobnovují" : ""}</span>
      </div>

      {r ? (
        <Row label="Rozsah">
          <div>
            {d.phase === "post" ? "Celkem" : "Zatím"} <b className="text-white">{n0(r.so_far_pts)} {unit}</b> = <b className="text-white">{cz(r.vs_typical, 2)}×</b> typického dne
            ({n0(d.typical_range_pts)} {unit})
            {cat && <> · <span style={{ color: cat[1] }} className="font-semibold">{cat[0]}</span></>}
            {r.percentile != null && d.phase === "rth" && <span className="text-gray-500"> · {cz(r.percentile, 0)}. percentil v tuto dobu</span>}
            {r.final_percentile != null && <span className="text-gray-500"> · {cz(r.final_percentile, 0)}. percentil všech dní</span>}
          </div>
          <div className="relative mt-1.5 h-1.5 rounded-full bg-[#232735]">
            <div className="h-full rounded-full bg-blue-500/80" style={{ width: `${bar}%` }} />
            <div className="absolute top-[-2px] h-2.5 w-px bg-white/60" style={{ left: `${100 / 2.5}%` }} title="typický den" />
          </div>
          {r.remaining_pts && (
            <div className="mt-1.5">
              Historicky odsud ještě přibude: medián <b className="text-white">+{n0(r.remaining_pts.p50)}</b>, ve 3 ze 4 dní do
              +{n0(r.remaining_pts.p75)}, v 9 z 10 do +{n0(r.remaining_pts.p90)} {unit}
              <span className="text-gray-500"> (dny s podobným rozsahem v {clock(open, r.checkpoint ?? 0)}, n={r.remaining_n})</span>
            </div>
          )}
        </Row>
      ) : (
        <Row label="Rozsah">
          RTH začíná v {clock(open, 0)} ET. Typický den teď: <b className="text-white">{n0(d.typical_range_pts)} {unit}</b>.
        </Row>
      )}

      {r && ex && d.phase === "rth" && (
        <Row label="High / low">
          <div>High {n0(r.high)} z {clock(open, r.t_high)} (stojí {ex.hi_age} min) vydrží do konce RTH: <Prob p={ex.high_holds} /></div>
          <div>Low {n0(r.low)} z {clock(open, r.t_low)} (stojí {ex.lo_age} min) vydrží do konce RTH: <Prob p={ex.low_holds} /></div>
        </Row>
      )}

      {tr && r && (
        <Row label="Trend">
          Efektivita pohybu {cz(tr.der, 2)}{tr.close_location != null && <> · cena v {cz(tr.close_location * 100, 0)} % denního rozsahu</>}
          {tr.p_trend_day && d.phase === "rth" && (
            <div>
              Dny s podobnou efektivitou skončily silným trendem {tr.direction === "up" ? "nahoru" : "dolů"}: <Prob p={tr.p_trend_day} />;
              {" "}pohyb pokračoval do close: <Prob p={tr.p_continues} binary />
            </div>
          )}
        </Row>
      )}

      {ss && ss.asia_high != null && (
        <Row label="Sessions">
          <div>Asie {n0(ss.asia_low)}–{n0(ss.asia_high)}
            {ss.pre && ss.pre !== "inside" && ss.pre !== "both" && ss.pre_stat && (
              <> · Pre-London vzal {ss.pre === "high" ? "high" : "low"} → London pokračoval dál: <Prob p={ss.pre_stat} /></>
            )}
          </div>
          {ss.scenario && ss.scenario_stat && (
            <div>
              {SCEN[ss.scenario]} → NY vezme London high <Prob p={ss.scenario_stat.ny_london_high} />
              {ss.ny_took_london_high ? <span className="text-green-400"> ✓ už</span> : null},
              {" "}London low <Prob p={ss.scenario_stat.ny_london_low} />
              {ss.ny_took_london_low ? <span className="text-green-400"> ✓ už</span> : null}
            </div>
          )}
          {ss.conditional && (
            <div className="text-gray-400">NY vzal nejdřív opačnou stranu → druhá strana později: <Prob p={ss.conditional} binary /></div>
          )}
        </Row>
      )}

      {d.macro.length > 0 && (
        <Row label="Makro">
          {d.macro.map((m) => (
            <div key={m.event}>
              Dnes {EVENT[m.event] ?? m.event}: rozsah dne historicky <b className="text-white">{cz(m.rth?.p50, 2)}×</b> typického
              {m.rth_ci && <span className="text-gray-500"> ({cz(m.rth_ci[0], 2)}–{cz(m.rth_ci[1], 2)}, n={m.n})</span>}
              {m.win?.p50 != null && <>, {m.window === "after14" ? "po 14:00" : "prvních 30 min"} {cz(m.win.p50, 2)}×</>}
            </div>
          ))}
        </Row>
      )}

      <p className="mt-2 text-[10px] text-gray-600">
        Historie {d.meta.stats_from} → {d.meta.stats_to} ({d.meta.days} seancí) · data dnes: {d.meta.src === "twelvedata" ? "Twelve Data" : "Yahoo"}.
        Frekvence z minulosti, ne obchodní signál ani win rate. Detail a metodika v <a href="/stats" className="underline">Statistikách</a>.
      </p>
    </div>
  );
}
