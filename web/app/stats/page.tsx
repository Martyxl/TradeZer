"use client";

import { useEffect, useState } from "react";
import { Info, X, ChevronDown, ChevronUp } from "lucide-react";

/* ---------------------------------------------------------------- typy */

interface SessionSize { avg: number; median: number; min: number; max: number }
interface MarketStats {
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
  by_hour: { volatility: number[]; volume: number[] };
}

/* ------------------------------------------------------------ pomocné */

const SESSION_LABELS: Record<string, string> = {
  asia: "Asia", london: "London", ny: "NY", close: "Close",
};
const REVISIT_LABELS: Record<string, string> = {
  same: "Stejný den", "1": "Následující den", "2": "2 dny", "3": "3 dny", never: "Nikdy",
};
const DAY_LABELS: Record<string, string> = {
  "1": "Den 1", "2": "Den 2", "3": "Den 3", never: "Ne do 3 dnů",
};
const SIDES_LABELS: Record<string, string> = {
  both: "Obě strany", high_only: "Pouze high", low_only: "Pouze low", neither: "Ani jedna",
};

function Bar({ label, value, accent = "#3b82f6", max = 100 }: {
  label: string; value: number; accent?: string; max?: number;
}) {
  const width = Math.max(2, (value / max) * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 shrink-0 text-gray-400 truncate">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-[#232735] overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${width}%`, background: accent }} />
      </div>
      <span className="w-12 text-right font-medium" style={{ color: value === max || value >= 50 ? accent : "#9ca3af" }}>
        {value.toFixed(1)} %
      </span>
    </div>
  );
}

function BarGroup({ data, labels, accents }: {
  data: Record<string, number>;
  labels: Record<string, string>;
  accents?: Record<string, string>;
}) {
  const entries = Object.entries(data).filter(([k, v]) => typeof v === "number" && labels[k]);
  return (
    <div className="space-y-2">
      {entries.map(([k, v]) => (
        <Bar key={k} label={labels[k]} value={v as number} accent={accents?.[k] ?? "#3b82f6"} />
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
      {subtitle && (
        <p className="text-[10px] uppercase tracking-wider text-gray-500 mt-0.5 mb-3">{subtitle}</p>
      )}
      {!subtitle && <div className="mb-3" />}
      {children}
    </div>
  );
}

/* --------------------------------------------------------------- modal */

const HELP: [string, string][] = [
  ["Session Sizes", "Průměrný / mediánový / min / max rozsah high–low každé session v bodech."],
  ["Daily HIGH/LOW — Session", "Ve které session se tiskne denní maximum/minimum. „Close“ = zbývající hodiny mimo hlavní sessions."],
  ["Daily Open Revisit", "Po otevření dne — jak brzy se cena vrátí k opening price (stejný den, den 1–3 později, nebo nikdy)."],
  ["Candle H/L Revisit", "U každé denní svíčky — jak brzy jsou její high a low znovu otestovány (den 1–3, nebo ne do 3 dnů)."],
  ["Daily NPOC Revisit", "Denní Naked Point of Control (cenová úroveň s největším objemem). Jak brzy je POC znovu navštíven."],
  ["Session NPOC", "Stejné jako Daily NPOC, ale počítané per session (Asia / London / NY). „Stejný den“ = revisit ještě tentýž obchodní den."],
  ["VWAP Edge Revisit", "Denní VWAP s pásmy ±1σ. Jakmile cena zasáhne okraj (±1σ), jak brzy se vrátí k VWAP linii."],
  ["Weekly HIGH/LOW — Day", "Který den v týdnu se tiskne týdenní maximum/minimum."],
  ["Weekly Open Revisit", "Den v týdnu, kdy se cena poprvé vrátí k týdennímu open."],
  ["Asia — Both Sides", "Během London+NY — je high/low Asia range prolomeno na obě strany, jen jednu, nebo žádnou? Pořadí: která strana padla první."],
  ["Globex — Both Sides", "Totéž pro overnight (Globex) range během NY RTH."],
  ["Volatility by Hour", "Průměrný hodinový rozsah high–low podle hodiny (UTC)."],
];

function HelpModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div
        className="bg-[#12141c] border border-[#2a2d3a] rounded-2xl max-w-3xl w-full p-6 my-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Jak číst tento report</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
        </div>
        <p className="text-sm text-gray-300 mb-4">
          <span className="text-blue-400 font-medium">Data:</span> Statistiky vycházejí z ~1 roku 5min svíček
          (Dukascopy). Všechny časy jsou v <span className="text-blue-400">UTC</span>. Obchodní den začíná
          ve <span className="text-blue-400">22:00 UTC</span>.
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
              <tr className="border-t border-[#2a2d3a]"><td className="px-3 py-2">NQ</td><td className="px-3 py-2">00–07</td><td className="px-3 py-2">07–12</td><td className="px-3 py-2">12–21</td><td className="px-3 py-2">13:30–20</td></tr>
              <tr className="border-t border-[#2a2d3a]"><td className="px-3 py-2">GOLD</td><td className="px-3 py-2">22–07</td><td className="px-3 py-2">07–12</td><td className="px-3 py-2">12–21</td><td className="px-3 py-2">13:30–18:30</td></tr>
            </tbody>
          </table>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {HELP.map(([t, d]) => (
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

/* ---------------------------------------------------- blok instrumentu */

function InstrumentBlock({ stats }: { stats: MarketStats }) {
  const [open, setOpen] = useState(true);
  const m = stats.meta;
  const sessionAccents = { asia: "#a855f7", london: "#3b82f6", ny: "#3b82f6", close: "#64748b" };

  return (
    <div className="rounded-2xl border border-[#2a2d3a] bg-[#12141c] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-[#161927] transition-colors"
      >
        <div className="h-9 w-9 rounded-full bg-blue-600 flex items-center justify-center text-xs font-bold text-white">
          {m.instrument === "NQ" ? "NQ" : "XAU"}
        </div>
        <div className="text-left">
          <div className="font-bold text-white">{m.label}</div>
          <div className="text-xs text-gray-500">
            {m.bars_m5.toLocaleString("cs")} 5m barů ({m.from} → {m.to}) · {m.days} dní · {m.weeks} týdnů
          </div>
        </div>
        <span className="ml-auto text-gray-500">{open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</span>
      </button>

      {open && (
        <div className="p-4 pt-0 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {/* Session Sizes */}
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
                        {SESSION_LABELS[k]}
                      </td>
                      <td className="text-right text-gray-300">{v.avg}</td>
                      <td className="text-right text-gray-300">{v.median}</td>
                      <td className="text-right text-gray-500">{v.min}</td>
                      <td className="text-right text-gray-500">{v.max}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card title="Daily HIGH — Session" subtitle={`${m.days} dní · kde se tiskne denní high`}>
              <BarGroup data={stats.daily_high_session} labels={SESSION_LABELS} accents={sessionAccents} />
            </Card>

            <Card title="Daily LOW — Session" subtitle={`${m.days} dní · kde se tiskne denní low`}>
              <BarGroup data={stats.daily_low_session} labels={SESSION_LABELS} accents={sessionAccents} />
            </Card>

            <Card title="Daily Open Revisit" subtitle={`${m.days} dní · cena se vrací k open`}>
              <BarGroup data={stats.daily_open_revisit} labels={REVISIT_LABELS} />
            </Card>

            <Card title="Candle H/L Revisit" subtitle={`${stats.candle_hl_revisit.levels} levelů · daily high & low retested`}>
              <BarGroup data={stats.candle_hl_revisit} labels={DAY_LABELS} />
            </Card>

            <Card title="Daily NPOC Revisit" subtitle={`${stats.daily_npoc_revisit.days} dní · POC retested`}>
              <BarGroup data={stats.daily_npoc_revisit} labels={DAY_LABELS} />
            </Card>

            <Card title="VWAP Edge Revisit" subtitle={`${stats.vwap_edge_revisit.days} dní · návrat k VWAP po ±1σ edge`}>
              <BarGroup data={stats.vwap_edge_revisit} labels={REVISIT_LABELS} />
            </Card>

            {Object.entries(stats.session_npoc_revisit).map(([sess, data]) => (
              <Card key={sess} title={`${SESSION_LABELS[sess]} NPOC Revisit`} subtitle={`${data.days} dní`}>
                <BarGroup data={data} labels={REVISIT_LABELS} />
              </Card>
            ))}

            <Card title="Weekly HIGH — Day" subtitle={`${m.weeks} týdnů`}>
              <BarGroup data={stats.weekly_high_day} labels={Object.fromEntries(Object.keys(stats.weekly_high_day).map(k => [k, k]))} />
            </Card>

            <Card title="Weekly LOW — Day" subtitle={`${m.weeks} týdnů`}>
              <BarGroup data={stats.weekly_low_day} labels={Object.fromEntries(Object.keys(stats.weekly_low_day).map(k => [k, k]))} />
            </Card>

            <Card title="Weekly Open Revisit" subtitle={`${m.weeks} týdnů · den prvního revisitu`}>
              <BarGroup data={stats.weekly_open_revisit} labels={Object.fromEntries(Object.keys(stats.weekly_open_revisit).map(k => [k, k]))} />
            </Card>

            <Card title="Asia — Both Sides" subtitle={`${stats.asia_both_sides.days} dní · during London+NY`}>
              <BarGroup data={stats.asia_both_sides} labels={SIDES_LABELS} />
              <div className="mt-3 pt-3 border-t border-[#232735] space-y-2">
                <Bar label="Low → High" value={stats.asia_both_sides.order?.low_to_high ?? 0} accent="#64748b" />
                <Bar label="High → Low" value={stats.asia_both_sides.order?.high_to_low ?? 0} accent="#64748b" />
              </div>
            </Card>

            <Card title="Globex — Both Sides" subtitle={`${stats.globex_both_sides.days} dní · during NY RTH`}>
              <BarGroup data={stats.globex_both_sides} labels={SIDES_LABELS} />
              <div className="mt-3 pt-3 border-t border-[#232735] space-y-2">
                <Bar label="Low → High" value={stats.globex_both_sides.order?.low_to_high ?? 0} accent="#64748b" />
                <Bar label="High → Low" value={stats.globex_both_sides.order?.high_to_low ?? 0} accent="#64748b" />
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <HourChart title="Volatility by Hour" values={stats.by_hour.volatility} unit={`průměrný rozsah / hod v ${m.unit}`} />
            <HourChart title="Volume by Hour" values={stats.by_hour.volume} unit="průměrný objem per 5m bar" />
          </div>
        </div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- page */

export default function StatsPage() {
  const [data, setData] = useState<MarketStats[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    Promise.allSettled(
      ["nq", "gold"].map((k) =>
        fetch(`/stats/${k}.json`, { cache: "no-store" }).then((r) => {
          if (!r.ok) throw new Error(`${k}: ${r.status}`);
          return r.json() as Promise<MarketStats>;
        })
      )
    ).then((results) => {
      const ok = results.filter((r): r is PromiseFulfilledResult<MarketStats> => r.status === "fulfilled").map((r) => r.value);
      if (ok.length === 0) setError("Statistiky nejsou k dispozici. Spusť data/compute_stats.py.");
      setData(ok);
    });
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-white">Market Statistics</h1>
        <button
          onClick={() => setShowHelp(true)}
          className="flex items-center gap-1.5 rounded-full border border-blue-800 bg-blue-950/40 px-3 py-1 text-xs text-blue-300 hover:bg-blue-900/40 transition-colors"
        >
          <Info size={13} /> Jak to funguje
        </button>
      </div>
      <p className="text-sm text-gray-400 -mt-3">
        Backtestované pravděpodobnosti a statistiky trhu napříč instrumenty
      </p>

      {error && (
        <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">{error}</div>
      )}

      {data.length === 0 && !error && (
        <div className="space-y-4">
          {[0, 1].map((i) => (
            <div key={i} className="h-24 rounded-2xl bg-[#151823] animate-pulse border border-[#2a2d3a]" />
          ))}
        </div>
      )}

      <div className="space-y-5">
        {data.map((s) => <InstrumentBlock key={s.meta.instrument} stats={s} />)}
      </div>

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  );
}
