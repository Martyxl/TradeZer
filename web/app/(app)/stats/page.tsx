"use client";

import { useEffect, useState } from "react";
import { Info, X, TrendingUp, Layers, Crosshair, LineChart, Target as TargetIcon, type LucideIcon } from "lucide-react";

/* ---------------------------------------------------------------- typy */

interface SessionSize { avg: number; median: number; min: number; max: number }
interface StatsBody {
  meta: {
    instrument: string; label: string; unit: string;
    from: string; to: string; bars_m5: number; days: number; weeks: number;
  };
  session_sizes: Record<string, SessionSize>;
  daily_high_session: Record<string, number>;
  daily_low_session: Record<string, number>;
  daily_open_revisit: Record<string, number>;
  candle_hl_revisit: Record<string, number>;
  daily_npoc_revisit: Record<string, number>;
  session_npoc_revisit: Record<string, Record<string, number>>;
  vwap_edge_revisit: Record<string, number>;
  weekly_high_day: Record<string, number>;
  weekly_low_day: Record<string, number>;
  weekly_open_revisit: Record<string, number>;
  asia_both_sides: Record<string, any>;
  globex_both_sides: Record<string, any>;
  first15_range?: {
    days: number;
    c23: Record<string, any>;
    eod: Record<string, any>;
  };
  trade_sim?: Record<string, TradeSimLeg | null>;
  by_hour: { volatility: number[]; volume: number[] };
}
interface TradeSimLeg {
  n_days: number; filled: number; fill_rate: number; offset_pct: number;
  win_rate: number; targets: Record<string, number>;
  avg_max_r: number; median_max_r: number; entry_min: number; run_min: number;
}
interface MarketStats extends StatsBody {
  prev?: StatsBody | null;
}

/* ------------------------------------------------------------ pomocné */

type LabelList = [string, string][];

const SESSION_LABELS: LabelList = [
  ["asia", "Asia"], ["london", "London"], ["ny", "NY"], ["close", "Close"],
];
const REVISIT_LABELS: LabelList = [
  ["same", "Stejný den"], ["1", "Následující den"], ["2", "2 dny"], ["3", "3 dny"], ["never", "Nikdy"],
];
const DAY_LABELS: LabelList = [
  ["1", "Den 1"], ["2", "Den 2"], ["3", "Den 3"], ["never", "Ne do 3 dnů"],
];
const SIDES_LABELS: LabelList = [
  ["both", "Obě strany"], ["high_only", "Pouze high"], ["low_only", "Pouze low"], ["neither", "Ani jedna"],
];
const SESSION_NAME: Record<string, string> = {
  asia: "Asia", london: "London", ny: "NY", close: "Close",
};

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

function Bar({ label, value, prev, accent = "#3b82f6", max = 100 }: {
  label: string; value: number; prev?: number; accent?: string; max?: number;
}) {
  const width = Math.max(2, (value / max) * 100);
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

function BarGroup({ data, prevData, labels, accents }: {
  data: Record<string, number>;
  prevData?: Record<string, number> | null;
  labels: LabelList;
  accents?: Record<string, string>;
}) {
  const entries = labels.filter(([k]) => typeof data[k] === "number");
  return (
    <div className="space-y-2">
      {entries.map(([k, label]) => (
        <Bar
          key={k}
          label={label}
          value={data[k]}
          prev={typeof prevData?.[k] === "number" ? prevData[k] : undefined}
          accent={accents?.[k] ?? "#3b82f6"}
        />
      ))}
    </div>
  );
}

function Card({ title, subtitle, children }: {
  title: string; subtitle?: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      {subtitle ? (
        <p className="text-[10px] uppercase tracking-wider text-gray-500 mt-0.5 mb-3">{subtitle}</p>
      ) : (
        <div className="mb-3" />
      )}
      {children}
    </div>
  );
}

function Section({ icon: Icon, title, description, children }: {
  icon: LucideIcon;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex items-center gap-2.5 mb-1">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-950/60 border border-blue-900/50">
          <Icon size={15} className="text-blue-400" />
        </span>
        <h2 className="text-base font-bold text-white">{title}</h2>
      </div>
      <p className="text-xs text-gray-500 mb-4 ml-[42px]">{description}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">{children}</div>
    </section>
  );
}

/* --------------------------------------------------------------- legenda */

const LEGEND: [string, string][] = [
  ["Session Sizes", "Průměrný / mediánový / min / max rozsah high–low každé session v bodech."],
  ["Daily HIGH/LOW — Session", "Ve které session se tiskne denní maximum/minimum. „Close“ = zbývající hodiny mimo hlavní sessions."],
  ["Daily Open Revisit", "Po otevření dne — jak brzy se cena vrátí k opening price (stejný den, den 1–3 později, nebo nikdy)."],
  ["Candle H/L Revisit", "U každé denní svíčky — jak brzy jsou její high a low znovu otestovány (den 1–3, nebo ne do 3 dnů)."],
  ["Daily NPOC Revisit", "Denní Naked Point of Control (cenová úroveň s největším objemem). Jak brzy je POC znovu navštíven."],
  ["Session NPOC", "Stejné jako Daily NPOC, ale počítané per session (Asia / London / NY). „Stejný den“ = revisit ještě tentýž obchodní den."],
  ["VWAP Edge Revisit", "Denní VWAP s pásmy ±1σ. Jakmile cena zasáhne okraj (±1σ), jak brzy se vrátí k VWAP linii."],
  ["Weekly HIGH/LOW — Day", "Který den v týdnu se tiskne týdenní maximum/minimum."],
  ["Weekly Open Revisit", "Den v týdnu, kdy se cena poprvé vrátí k týdennímu open."],
  ["First 15m Range", "První 15min svíčka po RTH open vytvoří range. Sledujeme, jestli 2.–3. svíčka (resp. zbytek seance) vybere její high, low, obě strany — a kterou stranu první (High → Low = sweep high, pak výběr low)."],
  ["Asia — Both Sides", "Během London+NY — je high/low Asia range prolomeno na obě strany, jen jednu, nebo žádnou? Pořadí: která strana padla první."],
  ["Globex — Both Sides", "Totéž pro overnight (Globex) range během NY RTH."],
  ["Volatility by Hour", "Průměrný hodinový rozsah high–low podle hodiny (UTC)."],
  ["Trading — backtest", "Simulace doporučeného vstupu: limit na offset (medián protipohybu) proti biasu po NY open, SL = 1R (=offset) za entry, TP na násobcích R. Ukazuje % obchodů, které dosáhly R1–R3 před SL, win rate (≥1R), medián/průměr max dosaženého R (potenciál) a časy (fill, peak). Vše podmíněno správným směrem — reálná výhoda = tato struktura × úspěšnost biasu."],
  ["▲▼ změny", "Šipky u hodnot ukazují posun oproti minulé měsíční aktualizaci dat (v procentních bodech)."],
];

function LegendModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div
        className="bg-[#12141c] border border-[#2a2d3a] rounded-2xl max-w-3xl w-full p-6 my-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Legenda</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
        </div>
        <p className="text-sm text-gray-300 mb-4">
          <span className="text-blue-400 font-medium">Data:</span> ~1 rok 5min svíček (Dukascopy),
          automaticky aktualizováno jednou měsíčně. Všechny časy v <span className="text-blue-400">UTC</span>,
          obchodní den začíná ve <span className="text-blue-400">22:00 UTC</span>.
        </p>
        <div className="text-xs text-gray-400 mb-4 rounded-lg border border-[#2a2d3a] overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="text-blue-400 bg-[#181b26]">
                <th className="text-left px-3 py-2">TRH</th><th className="text-left px-3 py-2">ASIA</th>
                <th className="text-left px-3 py-2">LONDON</th><th className="text-left px-3 py-2">NY</th>
                <th className="text-left px-3 py-2">RTH</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-[#2a2d3a]"><td className="px-3 py-2">NQ / YM</td><td className="px-3 py-2">00–07</td><td className="px-3 py-2">07–12</td><td className="px-3 py-2">12–21</td><td className="px-3 py-2">13:30–20</td></tr>
              <tr className="border-t border-[#2a2d3a]"><td className="px-3 py-2">GOLD</td><td className="px-3 py-2">22–07</td><td className="px-3 py-2">07–12</td><td className="px-3 py-2">12–21</td><td className="px-3 py-2">13:30–18:30</td></tr>
            </tbody>
          </table>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {LEGEND.map(([t, d]) => (
            <div key={t} className="rounded-lg border border-[#2a2d3a] bg-[#151823] p-3">
              <div className="text-blue-400 text-sm font-medium mb-1">{t}</div>
              <div className="text-xs text-gray-400">{d}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------- hodinový graf */

function HourChart({ title, values, unit }: { title: string; values: number[]; unit: string }) {
  const max = Math.max(...values, 1);
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <h3 className="text-sm font-semibold text-white mb-1">{title}</h3>
      <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-3">{unit} · UTC</p>
      <div className="flex items-end gap-[3px] h-24">
        {values.map((v, h) => (
          <div key={h} className="flex-1 flex flex-col items-center gap-1" title={`${h}:00 UTC — ${v}`}>
            <div className="w-full rounded-t bg-blue-500/80 hover:bg-blue-400 transition-colors" style={{ height: `${(v / max) * 100}%` }} />
          </div>
        ))}
      </div>
      <div className="flex gap-[3px] mt-1">
        {values.map((_, h) => (
          <div key={h} className="flex-1 text-center text-[8px] text-gray-600">{h % 4 === 0 ? h : ""}</div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------- trade sim karta */

function TradeSimCard({ dir, leg, unit }: { dir: "up" | "down"; leg: TradeSimLeg; unit: string }) {
  const isLong = dir === "up";
  const color = isLong ? "#4ade80" : "#f87171";
  const side = isLong ? "LONG" : "SHORT";
  const R_LEVELS = ["1.0", "1.5", "2.0", "2.5", "3.0"];

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold" style={{ color }}>{side}</span>
          <span className="text-[10px] text-gray-500">{leg.filled} obchodů · fill {leg.fill_rate}%</span>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold" style={{ color: leg.win_rate >= 50 ? color : "#9ca3af" }}>{leg.win_rate}%</div>
          <div className="text-[9px] text-gray-500 uppercase">win (≥1R)</div>
        </div>
      </div>

      {/* Setup: entry / SL / TP */}
      <div className="grid grid-cols-3 gap-2 mb-3 text-center">
        <div className="rounded-lg bg-[#0f1117] border border-[#2a2d3a] py-1.5">
          <div className="text-[9px] uppercase text-gray-500">Entry</div>
          <div className="text-xs font-semibold text-gray-200">{isLong ? "−" : "+"}{leg.offset_pct}%</div>
          <div className="text-[9px] text-gray-600">od NY open</div>
        </div>
        <div className="rounded-lg bg-[#0f1117] border border-red-900/40 py-1.5">
          <div className="text-[9px] uppercase text-gray-500">SL (1R)</div>
          <div className="text-xs font-semibold text-red-300">{leg.offset_pct}%</div>
          <div className="text-[9px] text-gray-600">za entry</div>
        </div>
        <div className="rounded-lg bg-[#0f1117] border border-green-900/40 py-1.5">
          <div className="text-[9px] uppercase text-gray-500">Potenciál</div>
          <div className="text-xs font-semibold text-green-300">{leg.median_max_r}R</div>
          <div className="text-[9px] text-gray-600">medián max</div>
        </div>
      </div>

      {/* R-target hit rates */}
      <div className="space-y-1.5 mb-3">
        <div className="text-[10px] uppercase tracking-wider text-gray-500">Dosažení TP (% fillnutých obchodů)</div>
        {R_LEVELS.map((r) => {
          const pct = leg.targets[r] ?? 0;
          return (
            <div key={r} className="flex items-center gap-2 text-xs">
              <span className="w-10 shrink-0 text-gray-400 font-mono">R{r}</span>
              <div className="flex-1 h-2 rounded-full bg-[#232735] overflow-hidden">
                <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
              </div>
              <span className="w-10 text-right font-medium" style={{ color: pct >= 50 ? color : "#9ca3af" }}>{pct}%</span>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-gray-500 border-t border-[#232735] pt-2">
        <span>Entry ~<span className="text-gray-400">{leg.entry_min} min</span> po NY open</span>
        <span>Peak ~<span className="text-gray-400">{leg.run_min} min</span></span>
        <span>Ø max <span className="text-gray-400">{leg.avg_max_r}R</span></span>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- page */

export default function StatsPage() {
  const [data, setData] = useState<Record<string, MarketStats>>({});
  const [selected, setSelected] = useState<string>("nq");
  const [error, setError] = useState<string | null>(null);
  const [showLegend, setShowLegend] = useState(false);

  useEffect(() => {
    Promise.allSettled(
      ["nq", "gold", "ym"].map((k) =>
        fetch(`/stats/${k}.json`, { cache: "no-store" }).then((r) => {
          if (!r.ok) throw new Error(`${k}: ${r.status}`);
          return r.json().then((j: MarketStats) => [k, j] as const);
        })
      )
    ).then((results) => {
      const ok = Object.fromEntries(
        results
          .filter((r): r is PromiseFulfilledResult<readonly [string, MarketStats]> => r.status === "fulfilled")
          .map((r) => r.value)
      );
      if (Object.keys(ok).length === 0) setError("Statistiky nejsou k dispozici. Spusť data/compute_stats.py.");
      setData(ok);
    });
  }, []);

  const stats = data[selected];
  const prev = stats?.prev ?? null;
  const m = stats?.meta;
  const sessionAccents = { asia: "#a855f7", london: "#3b82f6", ny: "#3b82f6", close: "#64748b" };
  const dayLabels = (d: Record<string, number>): LabelList =>
    Object.keys(d).map((k) => [k, k] as [string, string]);

  return (
    <div className="space-y-8">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-white">Market Statistics</h1>
          <button
            onClick={() => setShowLegend(true)}
            className="flex items-center gap-1.5 rounded-full border border-blue-800 bg-blue-950/40 px-3 py-1 text-xs text-blue-300 hover:bg-blue-900/40 transition-colors"
          >
            <Info size={13} /> Legenda
          </button>
        </div>
        <p className="text-sm text-gray-400 mt-1">
          Backtestované pravděpodobnosti a statistiky trhu napříč instrumenty
        </p>
      </div>

      {/* Filtr instrumentu */}
      <div className="flex items-center gap-2 -mt-4">
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
        {m && (
          <span className="ml-2 text-xs text-gray-500">
            {m.bars_m5.toLocaleString("cs")} 5m barů · {m.from} → {m.to} · {m.days} dní · {m.weeks} týdnů
            {prev && <> · změny vs. data k {prev.meta.to}</>}
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">{error}</div>
      )}

      {!stats && !error && (
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-40 rounded-2xl bg-[#151823] animate-pulse border border-[#2a2d3a]" />
          ))}
        </div>
      )}

      {stats && m && (
        <>
          {/* ============ SESSIONS ============ */}
          <Section
            icon={Layers}
            title="Sessions"
            description="Rozsahy a chování jednotlivých obchodních seancí (Asia / London / NY)"
          >
            <Card title="Session Sizes" subtitle={`průměrný rozsah v ${m.unit}`}>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 text-[10px] uppercase">
                    <th className="text-left pb-2">Session</th><th className="text-right pb-2">Průměr</th>
                    <th className="text-right pb-2">Medián</th><th className="text-right pb-2">Min</th>
                    <th className="text-right pb-2">Max</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(stats.session_sizes).map(([k, v]) => (
                    <tr key={k} className="border-t border-[#232735]">
                      <td className="py-1.5 font-medium" style={{ color: k === "asia" ? "#a855f7" : k === "ny" ? "#eab308" : "#3b82f6" }}>
                        {SESSION_NAME[k]}
                      </td>
                      <td className="text-right text-gray-300">
                        {v.avg}
                        {prev?.session_sizes?.[k] && Math.abs(v.avg - prev.session_sizes[k].avg) >= 1 && (
                          <span className="text-[9px] ml-1" style={{ color: v.avg > prev.session_sizes[k].avg ? "#4ade80" : "#f87171" }}>
                            {v.avg > prev.session_sizes[k].avg ? "▲" : "▼"}
                          </span>
                        )}
                      </td>
                      <td className="text-right text-gray-300">{v.median}</td>
                      <td className="text-right text-gray-500">{v.min}</td>
                      <td className="text-right text-gray-500">{v.max}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card title="Daily HIGH — Session" subtitle={`${m.days} dní · kde se tiskne denní high`}>
              <BarGroup data={stats.daily_high_session} prevData={prev?.daily_high_session} labels={SESSION_LABELS} accents={sessionAccents} />
            </Card>

            <Card title="Daily LOW — Session" subtitle={`${m.days} dní · kde se tiskne denní low`}>
              <BarGroup data={stats.daily_low_session} prevData={prev?.daily_low_session} labels={SESSION_LABELS} accents={sessionAccents} />
            </Card>

            <HourChart title="Volatility by Hour" values={stats.by_hour.volatility} unit={`průměrný rozsah / hod v ${m.unit}`} />
            <HourChart title="Volume by Hour" values={stats.by_hour.volume} unit="průměrný objem per 5m bar" />
          </Section>

          {/* ============ HIGHS & LOWS ============ */}
          <Section
            icon={TrendingUp}
            title="Highs & Lows"
            description="Retesty denních extrémů, týdenní maxima/minima a prolomení klíčových range"
          >
            {stats.first15_range && (
              <Card title="First 15m Range — 2. + 3. svíčka" subtitle={`${stats.first15_range.days} dní · sweep high/low první 15min po RTH open`}>
                <BarGroup data={stats.first15_range.c23} prevData={prev?.first15_range?.c23} labels={SIDES_LABELS} />
                <div className="mt-3 pt-3 border-t border-[#232735] space-y-2">
                  <Bar label="High → Low" value={stats.first15_range.c23.order?.high_to_low ?? 0} prev={prev?.first15_range?.c23?.order?.high_to_low} accent="#64748b" />
                  <Bar label="Low → High" value={stats.first15_range.c23.order?.low_to_high ?? 0} prev={prev?.first15_range?.c23?.order?.low_to_high} accent="#64748b" />
                </div>
              </Card>
            )}

            {stats.first15_range && (
              <Card title="First 15m Range — do konce RTH" subtitle={`${stats.first15_range.days} dní · sweep do konce seance`}>
                <BarGroup data={stats.first15_range.eod} prevData={prev?.first15_range?.eod} labels={SIDES_LABELS} />
                <div className="mt-3 pt-3 border-t border-[#232735] space-y-2">
                  <Bar label="High → Low" value={stats.first15_range.eod.order?.high_to_low ?? 0} prev={prev?.first15_range?.eod?.order?.high_to_low} accent="#64748b" />
                  <Bar label="Low → High" value={stats.first15_range.eod.order?.low_to_high ?? 0} prev={prev?.first15_range?.eod?.order?.low_to_high} accent="#64748b" />
                </div>
              </Card>
            )}

            <Card title="Candle H/L Revisit" subtitle={`${stats.candle_hl_revisit.levels} levelů · daily high & low retested`}>
              <BarGroup data={stats.candle_hl_revisit} prevData={prev?.candle_hl_revisit} labels={DAY_LABELS} />
            </Card>

            <Card title="Weekly HIGH — Day" subtitle={`${m.weeks} týdnů`}>
              <BarGroup data={stats.weekly_high_day} prevData={prev?.weekly_high_day} labels={dayLabels(stats.weekly_high_day)} />
            </Card>

            <Card title="Weekly LOW — Day" subtitle={`${m.weeks} týdnů`}>
              <BarGroup data={stats.weekly_low_day} prevData={prev?.weekly_low_day} labels={dayLabels(stats.weekly_low_day)} />
            </Card>

            <Card title="Asia — Both Sides" subtitle={`${stats.asia_both_sides.days} dní · during London+NY`}>
              <BarGroup data={stats.asia_both_sides} prevData={prev?.asia_both_sides} labels={SIDES_LABELS} />
              <div className="mt-3 pt-3 border-t border-[#232735] space-y-2">
                <Bar label="Low → High" value={stats.asia_both_sides.order?.low_to_high ?? 0} prev={prev?.asia_both_sides?.order?.low_to_high} accent="#64748b" />
                <Bar label="High → Low" value={stats.asia_both_sides.order?.high_to_low ?? 0} prev={prev?.asia_both_sides?.order?.high_to_low} accent="#64748b" />
              </div>
            </Card>

            <Card title="Globex — Both Sides" subtitle={`${stats.globex_both_sides.days} dní · during NY RTH`}>
              <BarGroup data={stats.globex_both_sides} prevData={prev?.globex_both_sides} labels={SIDES_LABELS} />
              <div className="mt-3 pt-3 border-t border-[#232735] space-y-2">
                <Bar label="Low → High" value={stats.globex_both_sides.order?.low_to_high ?? 0} prev={prev?.globex_both_sides?.order?.low_to_high} accent="#64748b" />
                <Bar label="High → Low" value={stats.globex_both_sides.order?.high_to_low ?? 0} prev={prev?.globex_both_sides?.order?.high_to_low} accent="#64748b" />
              </div>
            </Card>
          </Section>

          {/* ============ NPOC ============ */}
          <Section
            icon={Crosshair}
            title="NPOC"
            description="Naked Point of Control — kdy se cena vrací na úrovně s největším zobchodovaným objemem"
          >
            <Card title="Daily NPOC Revisit" subtitle={`${stats.daily_npoc_revisit.days} dní · POC retested`}>
              <BarGroup data={stats.daily_npoc_revisit} prevData={prev?.daily_npoc_revisit} labels={DAY_LABELS} />
            </Card>

            {Object.entries(stats.session_npoc_revisit).map(([sess, d]) => (
              <Card key={sess} title={`${SESSION_NAME[sess]} NPOC Revisit`} subtitle={`${d.days} dní`}>
                <BarGroup data={d} prevData={prev?.session_npoc_revisit?.[sess]} labels={REVISIT_LABELS} />
              </Card>
            ))}
          </Section>

          {/* ============ VWAP & OPENS ============ */}
          <Section
            icon={LineChart}
            title="VWAP & Opens"
            description="Návraty k VWAP linii a k denním/týdenním otevíracím cenám"
          >
            <Card title="VWAP Edge Revisit" subtitle={`${stats.vwap_edge_revisit.days} dní · návrat k VWAP po ±1σ edge`}>
              <BarGroup data={stats.vwap_edge_revisit} prevData={prev?.vwap_edge_revisit} labels={REVISIT_LABELS} />
            </Card>

            <Card title="Daily Open Revisit" subtitle={`${m.days} dní · cena se vrací k open`}>
              <BarGroup data={stats.daily_open_revisit} prevData={prev?.daily_open_revisit} labels={REVISIT_LABELS} />
            </Card>

            <Card title="Weekly Open Revisit" subtitle={`${m.weeks} týdnů · den prvního revisitu`}>
              <BarGroup data={stats.weekly_open_revisit} prevData={prev?.weekly_open_revisit} labels={dayLabels(stats.weekly_open_revisit)} />
            </Card>
          </Section>

          {/* ============ TRADING (backtest doporučení) ============ */}
          {stats.trade_sim && (
            <section>
              <div className="flex items-center gap-2.5 mb-1">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-950/60 border border-blue-900/50">
                  <TargetIcon size={15} className="text-blue-400" />
                </span>
                <h2 className="text-base font-bold text-white">Trading — backtest doporučení</h2>
              </div>
              <p className="text-xs text-gray-500 mb-4 ml-[42px]">
                Entry limit na offset proti biasu po NY open, SL = 1R (offset), TP na R1–R3.
                Simulace 5m bar po baru (SL má přednost). <span className="text-yellow-500/80">Podmíněno správným směrem
                (hindsight) — reálná výhoda = tohle × úspěšnost biasu.</span>
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {(["down", "up"] as const).map((d) => {
                  const leg = stats.trade_sim?.[d];
                  if (!leg) return null;
                  return <TradeSimCard key={d} dir={d} leg={leg} unit={m.unit} />;
                })}
              </div>
            </section>
          )}
        </>
      )}

      {showLegend && <LegendModal onClose={() => setShowLegend(false)} />}
    </div>
  );
}
