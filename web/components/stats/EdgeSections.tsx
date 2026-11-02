"use client";

// Statistiky „Edge“ (blok `edge` z data/edge_stats.py): rozsah dne a zbývající pohyb, kdy vznikají
// extrémy RTH, scénáře Asia → London → NY, trendový den a makro dny. Vše s n a 95% intervalem.

import { Activity, CalendarClock, Clock, Gauge, Route, type LucideIcon } from "lucide-react";
import { type P, Prob, ProbBar, clock, cz } from "./prob";

type Q = { n: number; p10?: number; p25?: number; p50?: number; p75?: number; p90?: number };
interface Bucket { lo: number | null; hi: number | null; ext: Q }
export interface Edge {
  meta: {
    rth_et: [number, number]; days: number; from: string | null; to: string | null; sources: Record<string, number>;
    ref_price: number | null; typical_range_pct: number | null; typical_first30_pct: number | null;
    typical_after14_pct: number | null; checkpoints: number[];
  };
  range?: { n: number; ratio: Q; checkpoints: Record<string, { n: number; ext: Q; buckets: Bucket[] }> };
  extremes?: {
    n: number;
    first30: Record<"high" | "low" | "either" | "both", P>;
    first60: Record<"high" | "low" | "either" | "both", P>;
    slots: { from: number; high: P; low: P }[];
    checkpoints: Record<string, Record<"high_done" | "low_done" | "both_done" | "high_done_aged" | "low_done_aged", P>>;
  };
  trend?: {
    n: number; der: Q; der_random_walk: number | null;
    der_share: Record<string, P>; close_location: Record<string, P>; retracement: Record<string, P>;
    trend_day: Record<"bull" | "bear" | "any", P>; strong_day: Record<"bull" | "bear" | "any", P>;
    first30_continuation: P;
    definition: { der_min: number; cl_min: number; retr_max: number; strong_der_min: number };
    checkpoints: Record<string, { n: number; buckets: { lo: number | null; hi: number | null; trend_day: P; continues: P }[] }>;
  };
  macro?: Record<string, any>;
  sessions?: {
    n: number; from: string | null; to: string | null; windows_et: Record<string, [number, number]>;
    london_vs_asia: Record<"high" | "low" | "both" | "inside", P>;
    pre_london: {
      pre_high: P; pre_low: P;
      after_pre_high: { london_ext_high: P; london_low: P };
      after_pre_low: { london_ext_low: P; london_high: P };
      narrow_after_pre_high: P; narrow_after_pre_low: P;
    };
    ny_by_scenario: Record<string, { n: number; share: P; ny_london_high: P; ny_london_low: P }>;
    high_only_low_first: P; low_only_high_first: P;
  };
}

const SRC: Record<string, string> = { twelvedata: "Twelve Data", own: "vlastní 5min data", yahoo: "Yahoo" };
const EVENT: Record<string, string> = { fomc: "FOMC (14:00 ET)", cpi: "CPI (8:30 ET)", nfp: "NFP (8:30 ET)", ppi: "PPI (8:30 ET)" };
const WINDOW: Record<string, string> = { after14: "14:00–close", first30: "prvních 30 min RTH" };
const SCEN: Record<string, string> = {
  both: "London vzal obě strany Asie", inside: "London zůstal uvnitř Asie",
  high_only: "London vzal jen Asia high", low_only: "London vzal jen Asia low",
};
const hh = (h: number) => `${Math.floor(h)}:${String(Math.round((h % 1) * 60)).padStart(2, "0")}`;

function Section({ icon: Icon, title, description, children }: { icon: LucideIcon; title: string; description: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="flex items-center gap-2.5 mb-1">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-950/60 border border-blue-900/50">
          <Icon size={15} className="text-blue-400" />
        </span>
        <h2 className="text-base font-bold text-white">{title}</h2>
      </div>
      <p className="text-xs text-gray-500 mb-4 ml-[42px]">{description}</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>
    </section>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4 min-w-0">
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <p className="text-[10px] uppercase tracking-wider text-gray-500 mt-0.5 mb-3">{subtitle}</p>
      {children}
    </div>
  );
}

export function EdgeSections({ edge, unit }: { edge: Edge; unit: string }) {
  const m = edge.meta;
  const open = m.rth_et[0];
  const typPts = m.typical_range_pct && m.ref_price ? (m.typical_range_pct / 100) * m.ref_price : null;
  const pts = (ratio?: number) => (ratio == null || typPts == null ? "—" : `${Math.round(ratio * typPts).toLocaleString("cs-CZ")}`);
  const srcText = Object.entries(m.sources).map(([k, v]) => `${SRC[k] ?? k} ${v}`).join(" + ");
  const period = `${m.from} → ${m.to} · ${m.days} seancí (${srcText})`;
  const r = edge.range, ex = edge.extremes, tr = edge.trend, mc = edge.macro, ss = edge.sessions;

  return (
    <div className="space-y-8">
      <div className="rounded-xl border border-blue-900/60 bg-blue-950/20 p-3 text-xs text-blue-200/90 leading-relaxed">
        Edge statistiky měří na našich datech to, co bývá v obchodních kurzech jen tvrzením. Rozsahy jsou v % ceny
        a vztažené k <b>typickému dni</b> (medián předchozích 20 seancí), takže jdou porovnat roky s jinou cenou
        i volatilitou; body = přepočet na aktuální cenu ({m.ref_price?.toLocaleString("cs-CZ")}). Pravděpodobnosti mají
        95% interval a počet dní, <span className="text-yellow-400/90">≈ náhoda</span> = neliší se od 50 %.
        {m.sources.twelvedata ? " U indexů je historie RTH z ETF (QQQ ≈ NQ, DIA ≈ YM) — procentní pohyb je prakticky shodný." : ""}
        {" "}RTH {hh(m.rth_et[0])}–{hh(m.rth_et[1])} ET. Frekvence není win rate a sama o sobě není obchodní signál.
      </div>

      {r && (
        <Section icon={Gauge} title="Rozsah dne a zbývající pohyb" description={`Jak velký bývá den a kolik pohybu historicky zbývá od daného času · ${period}`}>
          <Card title="Typický den a percentily" subtitle={`RTH rozsah · n=${r.n}`}>
            <div className="mb-3 text-sm text-gray-300">
              Typický den teď: <b className="text-white">{pts(1)} {unit}</b>
              <span className="text-xs text-gray-500"> ({cz(m.typical_range_pct, 2)} % ceny)</span>
            </div>
            <table className="w-full text-xs">
              <tbody>
                {([["p10", "10 % dní menší než"], ["p25", "čtvrtina dní pod"], ["p50", "medián"], ["p75", "běžný den do (75. pct.)"], ["p90", "extrémní den nad (90. pct.)"]] as const).map(([k, label]) => (
                  <tr key={k} className="border-t border-[#232735]">
                    <td className="py-1.5 text-gray-400">{label}</td>
                    <td className="text-right text-gray-500">{cz(r.ratio[k], 2)}× typického</td>
                    <td className="text-right font-medium text-white">{pts(r.ratio[k])} {unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[10px] text-gray-500">Kategorie dne: běžný ≤ 75. percentil, nadprůměrný 75.–90., extrémní nad 90. Jedno průměrné číslo jako denní cíl nefunguje — rozdělení je zešikmené k velkým dnům.</p>
          </Card>
          <Card title="Kolik ještě zbývá" subtitle="o kolik se rozsah RTH od daného času ještě rozšíří (medián · 75 % dní · 90 % dní)">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] uppercase text-gray-500">
                  <th className="text-left pb-1">Čas ET</th><th className="text-right pb-1">zatím malý den</th>
                  <th className="text-right pb-1">střední</th><th className="text-right pb-1">velký</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(r.checkpoints).map(([c, v]) => (
                  <tr key={c} className="border-t border-[#232735]">
                    <td className="py-1.5 text-gray-400">{clock(open, +c)}</td>
                    {v.buckets.map((b, i) => (
                      <td key={i} className="text-right text-gray-300" title={`n=${b.ext.n}`}>
                        +{pts(b.ext.p50)} <span className="text-gray-500">/ {pts(b.ext.p75)} / {pts(b.ext.p90)}</span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[10px] text-gray-500">„Malý / střední / velký“ = třetiny dní podle rozsahu do daného času. Počítá se jen z dat známých v tu chvíli (bez pohledu do budoucnosti). Živě pro dnešek viz karta „Dnešní den v číslech“.</p>
          </Card>
        </Section>
      )}

      {ex && (
        <Section icon={Clock} title="Kdy vznikají high a low RTH" description={`Denní extrémy RTH (ne Globex) · ${period}`}>
          <Card title="Úvod seance" subtitle={`n=${ex.n} dní`}>
            <div className="space-y-2">
              <ProbBar label="High i/nebo low v 1. hodině" p={ex.first60.either} />
              <ProbBar label="Low v 1. hodině" p={ex.first60.low} accent="#f87171" />
              <ProbBar label="High v 1. hodině" p={ex.first60.high} accent="#4ade80" />
              <ProbBar label="Oba v 1. hodině" p={ex.first60.both} accent="#64748b" />
              <ProbBar label="Extrém v prvních 30 min" p={ex.first30.either} />
            </div>
            <div className="mt-4 text-[10px] uppercase tracking-wider text-gray-500 mb-1">Kdy vzniká (30min sloty)</div>
            <div className="flex items-end gap-[3px] h-20">
              {ex.slots.map((s) => {
                const mx = Math.max(...ex.slots.map((x) => Math.max(x.high.pct ?? 0, x.low.pct ?? 0)), 1);
                return (
                  <div key={s.from} className="flex-1 flex items-end gap-px h-full" title={`${clock(open, s.from)} · high ${cz(s.high.pct)} % · low ${cz(s.low.pct)} %`}>
                    <div className="flex-1 rounded-t bg-green-500/70" style={{ height: `${((s.high.pct ?? 0) / mx) * 100}%` }} />
                    <div className="flex-1 rounded-t bg-red-500/70" style={{ height: `${((s.low.pct ?? 0) / mx) * 100}%` }} />
                  </div>
                );
              })}
            </div>
            <div className="flex gap-[3px] mt-1">
              {ex.slots.map((s, i) => <div key={s.from} className="flex-1 text-center text-[8px] text-gray-600">{i % 2 === 0 ? clock(open, s.from) : ""}</div>)}
            </div>
          </Card>
          <Card title="Stojí už high / low?" subtitle="podíl dní, kdy po daném čase už nový extrém RTH nevznikl">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] uppercase text-gray-500">
                  <th className="text-left pb-1">Čas ET</th><th className="text-right pb-1">high hotové</th><th className="text-right pb-1">low hotové</th><th className="text-right pb-1">obojí</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ex.checkpoints).map(([c, v]) => (
                  <tr key={c} className="border-t border-[#232735]">
                    <td className="py-1.5 text-gray-400">{clock(open, +c)}</td>
                    <td className="text-right text-gray-200" title={`stojí-li high už 30+ min: ${cz(v.high_done_aged.pct)} %`}>{cz(v.high_done.pct)} %</td>
                    <td className="text-right text-gray-200" title={`stojí-li low už 30+ min: ${cz(v.low_done_aged.pct)} %`}>{cz(v.low_done.pct)} %</td>
                    <td className="text-right text-gray-400">{cz(v.both_done.pct)} %</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[10px] text-gray-500">Neříká nic o směru ani o velikosti zbytku dne. Najetím myši: šance, když extrém stojí už aspoň 30 minut.</p>
          </Card>
        </Section>
      )}

      {ss && (
        <Section icon={Route} title="Asia → Pre-London → London → NY" description={`Scénáře proražení session range · ${ss.from} → ${ss.to} · ${ss.n} dní · okna ET: Asia ${ss.windows_et.asia.map(hh).join("–")}, Pre-London ${ss.windows_et.pre.map(hh).join("–")}, London ${ss.windows_et.london.map(hh).join("–")}, NY ${ss.windows_et.ny.map(hh).join("–")}`}>
          <Card title="London vs. Asian range" subtitle={`n=${ss.n}`}>
            <div className="space-y-2">
              <ProbBar label="London vezme Asia high" p={ss.london_vs_asia.high} accent="#4ade80" />
              <ProbBar label="London vezme Asia low" p={ss.london_vs_asia.low} accent="#f87171" />
              <ProbBar label="Obě strany" p={ss.london_vs_asia.both} accent="#a855f7" />
              <ProbBar label="Ani jednu" p={ss.london_vs_asia.inside} accent="#64748b" />
            </div>
            <div className="mt-4 text-[10px] uppercase tracking-wider text-gray-500 mb-2">Když už Pre-London prorazil</div>
            <div className="space-y-1.5 text-xs text-gray-300">
              <div>Pre-London vzal high ({cz(ss.pre_london.pre_high.pct)} % dní) → London udělá ještě vyšší high: <Prob p={ss.pre_london.after_pre_high.london_ext_high} /></div>
              <div className="pl-3 text-gray-500">úzká Asie: <Prob p={ss.pre_london.narrow_after_pre_high} /> · London přesto vezme Asia low: <Prob p={ss.pre_london.after_pre_high.london_low} /></div>
              <div>Pre-London vzal low ({cz(ss.pre_london.pre_low.pct)} % dní) → London udělá ještě nižší low: <Prob p={ss.pre_london.after_pre_low.london_ext_low} /></div>
              <div className="pl-3 text-gray-500">úzká Asie: <Prob p={ss.pre_london.narrow_after_pre_low} /> · London přesto vezme Asia high: <Prob p={ss.pre_london.after_pre_low.london_high} /></div>
            </div>
          </Card>
          <Card title="Co udělá NY s London range" subtitle="podle toho, jak London naložil s Asií">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] uppercase text-gray-500">
                  <th className="text-left pb-1">Scénář Londýna</th><th className="text-right pb-1">dní</th>
                  <th className="text-right pb-1">NY vezme L. high</th><th className="text-right pb-1">NY vezme L. low</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ss.ny_by_scenario).map(([k, v]) => (
                  <tr key={k} className="border-t border-[#232735]">
                    <td className="py-1.5 text-gray-300">{SCEN[k]}</td>
                    <td className="text-right text-gray-500">{cz(v.share.pct)} %</td>
                    <td className="text-right text-gray-200" title={`95% ${v.ny_london_high.ci?.join("–")} %, n=${v.n}`}>{cz(v.ny_london_high.pct)} %</td>
                    <td className="text-right text-gray-200" title={`95% ${v.ny_london_low.ci?.join("–")} %, n=${v.n}`}>{cz(v.ny_london_low.pct)} %</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-3 space-y-1.5 text-xs text-gray-300">
              <div>London jen high a NY vezme nejdřív London low → později i London high: <Prob p={ss.high_only_low_first} binary /></div>
              <div>London jen low a NY vezme nejdřív London high → později i London low: <Prob p={ss.low_only_high_first} binary /></div>
            </div>
            <p className="mt-2 text-[10px] text-gray-500">NY testuje extrémy Londýna velmi často v každém scénáři — samotné proražení je slabý signál. „Úzká Asie“ = spodní třetina vůči typické Asii (medián 20 dní).</p>
          </Card>
        </Section>
      )}

      {tr && (
        <Section icon={Activity} title="Trendový den" description={`Objektivní měření místo „bylo to vidět“ · ${period}`}>
          <Card title="Efektivita pohybu (DER)" subtitle="|close − open| / součet všech 5min pohybů">
            <table className="w-full text-xs mb-3">
              <tbody>
                <tr className="border-t border-[#232735]"><td className="py-1.5 text-gray-400">medián DER</td><td className="text-right text-white font-medium">{cz(tr.der.p50, 3)}</td></tr>
                <tr className="border-t border-[#232735]"><td className="py-1.5 text-gray-400">náhodná procházka (1/√N)</td><td className="text-right text-gray-300">{cz(tr.der_random_walk, 3)}</td></tr>
                <tr className="border-t border-[#232735]"><td className="py-1.5 text-gray-400">90 % dní pod</td><td className="text-right text-gray-300">{cz(tr.der.p90, 3)}</td></tr>
              </tbody>
            </table>
            <div className="space-y-2">
              <ProbBar label={`Trend. den dle kurzu (DER ≥ ${cz(tr.definition.der_min, 2)})`} p={tr.trend_day.any} accent="#64748b" />
              <ProbBar label={`Silný trend. den (DER ≥ ${cz(tr.definition.strong_der_min, 2)})`} p={tr.strong_day.any} />
              <ProbBar label="… z toho býčí" p={tr.strong_day.bull} accent="#4ade80" />
              <ProbBar label="… z toho medvědí" p={tr.strong_day.bear} accent="#f87171" />
            </div>
            <p className="mt-2 text-[10px] text-gray-500">
              Trendový den = DER nad prahem, close v krajní pětině rozsahu (≥ {cz(tr.definition.cl_min * 100, 0)} % / ≤ {cz(100 - tr.definition.cl_min * 100, 0)} %) a max. retracement ≤ {cz(tr.definition.retr_max * 100, 0)} % rozsahu.
              Práh 0,5 z kurzů prakticky nenastává (typický den je blízko náhodné procházky), proto „silný“ den = horních 10 % DER.
            </p>
          </Card>
          <Card title="Close location a směr prvních 30 minut" subtitle={`n=${tr.n}`}>
            <div className="space-y-2">
              <ProbBar label="Close u high (≥ 80 %)" p={tr.close_location.near_high} accent="#4ade80" />
              <ProbBar label="Horní část" p={tr.close_location.upper} accent="#86efac" />
              <ProbBar label="Střed" p={tr.close_location.mid} accent="#64748b" />
              <ProbBar label="Dolní část" p={tr.close_location.lower} accent="#fca5a5" />
              <ProbBar label="Close u low (≤ 20 %)" p={tr.close_location.near_low} accent="#f87171" />
            </div>
            <div className="mt-4 space-y-2">
              <ProbBar label="Směr 1. 30 min pokračuje do close" p={tr.first30_continuation} binary />
            </div>
            {tr.checkpoints["60"] && (
              <div className="mt-3 text-xs text-gray-300">
                <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Podle efektivity v {clock(open, 60)} ET</div>
                {tr.checkpoints["60"].buckets.map((b, i) => (
                  <div key={i} className="flex flex-wrap justify-between gap-x-3 border-t border-[#232735] py-1">
                    <span className="text-gray-400">DER {b.lo == null ? `< ${cz(b.hi, 2)}` : b.hi == null ? `≥ ${cz(b.lo, 2)}` : `${cz(b.lo, 2)}–${cz(b.hi, 2)}`}</span>
                    <span>silný trend: <Prob p={b.trend_day} /></span>
                    <span>pokračuje: <Prob p={b.continues} binary /></span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Section>
      )}

      {mc && (
        <Section icon={CalendarClock} title="Makro dny" description={`Rozsah v den zveřejnění vůči typickému dni (1,0× = běžný den) · ${period}`}>
          <Card title="Rozsah dne a okna kolem zprávy" subtitle="medián poměru (95% interval) · n dní">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] uppercase text-gray-500">
                  <th className="text-left pb-1">Událost</th><th className="text-right pb-1">celé RTH</th><th className="text-right pb-1">okno</th><th className="text-right pb-1">extrémní den</th>
                </tr>
              </thead>
              <tbody>
                {["fomc", "cpi", "nfp", "ppi"].filter((k) => mc[k]).map((k) => {
                  const v = mc[k];
                  const ci = v.rth_ci as [number, number] | null;
                  const sig = ci && (ci[0] > 1 || ci[1] < 1);
                  return (
                    <tr key={k} className="border-t border-[#232735]">
                      <td className="py-1.5 text-gray-300">{EVENT[k]} <span className="text-gray-600">n={v.n}</span></td>
                      <td className="text-right" title={ci ? `95% ${ci.join("–")}` : ""}>
                        <span className={sig ? "font-semibold text-white" : "text-gray-400"}>{cz(v.rth?.p50, 2)}×</span>
                        {!sig && <span className="ml-1 text-[10px] text-yellow-500/80">≈ běžný</span>}
                      </td>
                      <td className="text-right text-gray-300" title={v.window ? WINDOW[v.window] : ""}>{v.win?.p50 != null ? `${cz(v.win.p50, 2)}×` : "—"}</td>
                      <td className="text-right text-gray-400">{v.big_day?.pct != null ? `${cz(v.big_day.pct)} %` : "—"}</td>
                    </tr>
                  );
                })}
                <tr className="border-t border-[#232735]"><td className="py-1.5 text-gray-500">dny bez těchto zpráv</td><td className="text-right text-gray-500">{cz(mc.none?.rth?.p50, 2)}×</td><td /><td className="text-right text-gray-600">10 %</td></tr>
              </tbody>
            </table>
            <p className="mt-2 text-[10px] text-gray-500">
              Okno: FOMC 14:00–close, CPI/NFP/PPI prvních 30 min RTH (zprávy vycházejí v 8:30, před otevřením). „Extrémní den“ = rozsah nad 90. percentilem běžných dní.
              Vyšší volatilita ≠ vyšší příležitost: širší spread, skluz a falešná proražení. Směr z toho neplyne.
              {m.rth_et[1] <= 14 ? " Pozor: RTH zlata (COMEX) končí ve 13:30, tedy PŘED FOMC — nižší poměr = čekání na Fed." : ""}
            </p>
          </Card>
        </Section>
      )}
    </div>
  );
}
