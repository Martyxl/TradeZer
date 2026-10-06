"use client";

import { useEffect, useState } from "react";
import { Bot, TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight, Scissors } from "lucide-react";

interface Pos {
  symbol: string; name: string | null; quantity: number; avg_cost: number; currency: string;
  last_price: number | null; value_czk: number | null; unrealized_czk: number | null;
  weight_pct: number | null; opened_at: string | null; conviction: number | null;
}
interface Trade {
  ts: string; action: string; symbol: string; name: string | null; quantity: number; price: number;
  currency: string; value_czk: number | null; realized_czk: number | null; conviction: number | null; reason: string;
}
interface Snap { date: string; equity: number; cash: number; invested: number; benchmark?: number | null; }
interface FundData {
  state: { start_capital: number; cash: number; equity: number; base: string; as_of: string | null;
           note: string | null; pnl: number; pnl_pct: number } | null;
  positions: Pos[]; trades: Trade[]; snapshots: Snap[]; note?: string;
}

const fmt = (n: number | null | undefined) => (n === null || n === undefined ? "—" : Math.round(n).toLocaleString("cs-CZ"));
const pnlC = (n: number | null | undefined) => (n == null ? "text-gray-400" : n > 0 ? "text-[#60ff82]" : n < 0 ? "text-[#ff5050]" : "text-gray-300");

export default function FondPage() {
  const [d, setD] = useState<FundData | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    fetch("/api/fund", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setD).catch(() => setErr(true));
  }, []);

  if (err) return <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-6 text-sm text-yellow-300">Fond není dostupný.</div>;
  if (!d) return <div className="h-64 animate-pulse rounded-2xl border border-[#2a2d3a] bg-[#151823]" />;

  const s = d.state;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[rgba(96,255,130,0.12)] border border-[rgba(96,255,130,0.3)]">
            <Bot size={16} className="text-[#60ff82]" />
          </span>
          <h1 className="text-2xl font-bold text-white">TRADEZER investuje</h1>
        </div>
        <p className="mt-1 text-sm text-gray-400">
          Náš AI fond obchoduje <b className="text-gray-300">podle vlastních analýz</b> (valuace, momentum, insideři, dark pool).
          Sleduj každý pohyb i proč. Start 1 000 000 Kč, paper-trading.
        </p>
        <p className="mt-2 inline-block rounded-lg border border-[#2a2d3a] bg-[#12141c] px-3 py-1.5 text-[11px] text-gray-400">
          <b className="text-gray-300">Konvikce</b> = naše skóre přesvědčení o obchodu <b>0–100</b> (čím vyšší, tím silnější signál).
          Skládá se z valuace, momentum, nákupů insiderů a dark-pool objemu.
        </p>
      </div>

      {!s ? (
        <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-8 text-center text-gray-400">Fond ještě nezačal obchodovat.</div>
      ) : (
        <>
          {/* strategie / note */}
          {s.note && (() => {
            // engine posílá poznámku jako "YYYY-MM-DD|text" (datum tahu); starší data bez prefixu
            const m = s.note!.match(/^(\d{4})-(\d{2})-(\d{2})\|([\s\S]*)$/);
            const when = m ? `${+m[3]}. ${+m[2]}.` : null;
            const text = m ? m[4] : s.note;
            return (
              <div className="rounded-xl border border-[rgba(96,255,130,0.25)] bg-[#0c1a11] px-4 py-3 text-sm text-[#cfeedd]">
                <span className="text-[11px] uppercase tracking-wider text-[#8fffab]">
                  Poslední tah fondu{when ? ` · ${when}` : ""}
                </span>
                <div className="mt-0.5">{text}</div>
              </div>
            );
          })()}
          {s.as_of && (
            <p className="-mt-3 text-[11px] text-gray-500">
              Ceny přepočítány {new Date(/[zZ]$|[+-]\d\d:?\d\d$/.test(s.as_of) ? s.as_of : s.as_of + "Z").toLocaleString("cs-CZ", { day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" })}
              {" "}· přecenění běží každou hodinu v obchodní době USA
            </p>
          )}

          {/* souhrn */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card label="Vklad (kapitál)" value={`${fmt(s.start_capital)} Kč`} />
            <Card label="Hodnota pozic" value={`${fmt(s.equity - s.cash)} Kč`} sub={`${d.positions.length} ${d.positions.length === 1 ? "pozice" : d.positions.length < 5 ? "pozice" : "pozic"} · za kolik nakoupeno (tržní)`} />
            <Card label="Hotovost" value={`${fmt(s.cash)} Kč`} sub="zatím neinvestováno" />
            <Card label="Celková hodnota + výnos" value={`${fmt(s.equity)} Kč`} sub={`výnos ${s.pnl >= 0 ? "+" : ""}${fmt(s.pnl)} Kč (${s.pnl_pct >= 0 ? "+" : ""}${s.pnl_pct} %)`} color={pnlC(s.pnl)} big />
          </div>

          {/* equity křivka */}
          <EquityChart snaps={d.snapshots} start={s.start_capital} />

          {/* pozice */}
          {d.positions.length > 0 && (
            <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
              <div className="border-b border-[#2a2d3a] px-4 py-3 text-sm font-semibold text-white">Pozice fondu</div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[11px] uppercase text-gray-500">
                      <th className="px-4 py-2 font-medium">Ticker</th>
                      <th className="px-4 py-2 font-medium text-right">Počet</th>
                      <th className="px-4 py-2 font-medium text-right">Prům. cena</th>
                      <th className="px-4 py-2 font-medium text-right">Hodnota</th>
                      <th className="px-4 py-2 font-medium text-right">Váha</th>
                      <th className="px-4 py-2 font-medium text-right">P/L</th>
                      <th className="px-4 py-2 font-medium text-right" title="Skóre přesvědčení 0–100 (valuace + momentum + insideři + dark pool). Vyšší = silnější signál.">Konvikce ⓘ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.positions.map((p) => (
                      <tr key={p.symbol} className="border-t border-[#20242f]">
                        <td className="px-4 py-2.5"><div className="font-medium text-white">{p.symbol}</div>{p.name && <div className="text-[11px] text-gray-500 truncate max-w-[160px]">{p.name}</div>}</td>
                        <td className="px-4 py-2.5 text-right text-gray-300">{p.quantity.toLocaleString("cs-CZ", { maximumFractionDigits: 2 })}</td>
                        <td className="px-4 py-2.5 text-right text-gray-400">{p.avg_cost.toFixed(2)} {p.currency}</td>
                        <td className="px-4 py-2.5 text-right text-gray-200">{fmt(p.value_czk)} Kč</td>
                        <td className="px-4 py-2.5 text-right text-gray-400">{p.weight_pct ?? "—"} %</td>
                        <td className={`px-4 py-2.5 text-right ${pnlC(p.unrealized_czk)}`}>{p.unrealized_czk == null ? "—" : `${p.unrealized_czk >= 0 ? "+" : ""}${fmt(p.unrealized_czk)}`}</td>
                        <td className="px-4 py-2.5 text-right"><span className="rounded bg-[#1e2536] px-1.5 py-0.5 text-[11px] text-gray-300">{p.conviction ?? "—"}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* trade log s důvody */}
          <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-5">
            <h2 className="text-sm font-semibold text-white">Deník obchodů — co a proč to fond udělal</h2>
            <p className="mt-0.5 text-[11px] text-gray-500">U každého obchodu je rozepsané, proč nakoupil/prodal a jak silná byla konvikce.</p>
            <div className="mt-3 space-y-2">
              {d.trades.length === 0 && <div className="text-sm text-gray-500">Zatím žádné obchody.</div>}
              {d.trades.map((t, i) => {
                const buy = t.action === "buy";
                const trim = t.action === "trim";
                const Icon = buy ? ArrowUpRight : trim ? Scissors : ArrowDownRight;
                const col = buy ? "text-[#60ff82]" : trim ? "text-amber-300" : "text-[#ff5050]";
                const bg = buy ? "bg-[rgba(96,255,130,0.1)]" : trim ? "bg-amber-500/10" : "bg-red-500/10";
                return (
                  <div key={i} className="flex gap-3 rounded-lg border border-[#20242f] bg-[#12141c] p-3">
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${bg}`}><Icon size={15} className={col} /></div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className={`text-sm font-semibold ${col}`}>{buy ? "Nákup" : trim ? "Ořez" : "Prodej"}</span>
                        <span className="font-medium text-white">{t.symbol}</span>
                        <span className="text-xs text-gray-400">{t.quantity.toLocaleString("cs-CZ", { maximumFractionDigits: 2 })} ks @ {t.price.toFixed(2)} {t.currency}</span>
                        <span className="text-xs text-gray-600">· {fmt(t.value_czk)} Kč</span>
                        {t.realized_czk != null && <span className={`text-xs ${pnlC(t.realized_czk)}`}>· realizováno {t.realized_czk >= 0 ? "+" : ""}{fmt(t.realized_czk)} Kč</span>}
                        <span className="ml-auto text-[11px] text-gray-600">{t.ts.replace("T", " ").slice(0, 16)}</span>
                      </div>
                      <div className="mt-1 text-[13px] leading-relaxed text-gray-200">{t.reason}</div>
                      {t.conviction != null && <div className="mt-0.5 text-[11px] text-gray-500">konvikce {Math.round(t.conviction)}/100</div>}
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="mt-4 text-[11px] text-gray-500">
              Demonstrační AI fond (paper-trading, virtuální peníze) — ukazuje, jak naše analýzy fungují v praxi. Řídí ho Spark na základě signálů aplikace.
              <b> Není investiční doporučení.</b> Minulá výkonnost nezaručuje budoucí.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

function Card({ label, value, sub, color = "text-white", big }: { label: string; value: string; sub?: string; color?: string; big?: boolean }) {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <div className="text-[11px] uppercase text-gray-500">{label}</div>
      <div className={`mt-1 font-bold ${big ? "text-2xl" : "text-lg"} ${color}`}>{value}</div>
      {sub && <div className={`text-xs ${color}`}>{sub}</div>}
    </div>
  );
}

function EquityChart({ snaps, start }: { snaps: Snap[]; start: number }) {
  if (snaps.length < 2) {
    return (
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-white"><TrendingUp size={15} className="text-[#60ff82]" /> Vývoj celkové hodnoty fondu</h2>
        <div className="py-8 text-center text-sm text-gray-500">Křivka se plní každý den — zatím {snaps.length === 1 ? "1 bod" : "0 bodů"}. Zítra přibude další.</div>
      </div>
    );
  }
  const toT = (s: string) => new Date(s + "T00:00:00").getTime();
  const tMin = toT(snaps[0].date), tMax = toT(snaps[snaps.length - 1].date), span = Math.max(tMax - tMin, 1);
  const hasBench = snaps.some((s) => s.benchmark != null);
  const benchVals = hasBench ? snaps.map((s) => s.benchmark ?? start) : [];
  const vals = snaps.map((s) => s.equity).concat([start], benchVals);
  const maxV = Math.max(...vals) * 1.02, minV = Math.min(...vals) * 0.98;
  const x = (t: number) => ((t - tMin) / span) * 100;
  const y = (v: number) => 100 - ((v - minV) / (maxV - minV)) * 100;
  const line = "M " + snaps.map((s) => `${x(toT(s.date)).toFixed(2)},${y(s.equity).toFixed(2)}`).join(" L ");
  const benchLine = hasBench ? "M " + snaps.map((s) => `${x(toT(s.date)).toFixed(2)},${y(s.benchmark ?? start).toFixed(2)}`).join(" L ") : "";
  const startY = y(start).toFixed(2);
  const last = snaps[snaps.length - 1];
  const up = last.equity >= start;
  const fundRet = (last.equity / start - 1) * 100;
  const benchRet = hasBench && last.benchmark ? (last.benchmark / start - 1) * 100 : null;
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
          {up ? <TrendingUp size={15} className="text-[#60ff82]" /> : <TrendingDown size={15} className="text-[#ff5050]" />} Vývoj celkové hodnoty fondu
        </h2>
        <span className="text-[11px] text-gray-500">{snaps[0].date} → {last.date}</span>
      </div>
      {benchRet != null && (
        <div className="mt-1 flex flex-wrap gap-x-4 text-[11px]">
          <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-3" style={{ background: up ? "#60ff82" : "#ff5050" }} /> Fond <b className={fundRet >= 0 ? "text-[#60ff82]" : "text-[#ff5050]"}>{fundRet >= 0 ? "+" : ""}{fundRet.toFixed(1)} %</b></span>
          <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-3 bg-gray-500" /> S&amp;P 500 <b className="text-gray-300">{benchRet >= 0 ? "+" : ""}{benchRet.toFixed(1)} %</b></span>
          <span className={fundRet >= benchRet ? "text-[#60ff82]" : "text-[#ff8080]"}>{fundRet >= benchRet ? "poráží index" : "zaostává za indexem"} o {Math.abs(fundRet - benchRet).toFixed(1)} b.</span>
        </div>
      )}
      <div className="relative mt-3 h-52 w-full">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full">
          <line x1="0" y1={startY} x2="100" y2={startY} stroke="#4b5563" strokeWidth="1" strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
          {benchLine && <path d={benchLine} fill="none" stroke="#9ca3af" strokeWidth="1.3" strokeDasharray="3 2" vectorEffect="non-scaling-stroke" />}
          <path d={line} fill="none" stroke={up ? "#60ff82" : "#ff5050"} strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
        </svg>
        <span className="absolute left-0 text-[10px] text-gray-600" style={{ top: `${startY}%` }}>start 1 mil.</span>
      </div>
    </div>
  );
}
