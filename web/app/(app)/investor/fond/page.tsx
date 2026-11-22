"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bot } from "lucide-react";
import { Card, Disclaimer, KindPill, Stat } from "@/components/investor/ui";
import { fmtCzk, fmtPct } from "@/components/investor/data";

interface Pos { symbol: string; name: string | null; weight_pct: number | null; value_czk: number | null }
interface Trade { ts: string; action: string; symbol: string; name: string | null; reason: string }
interface Snap { date: string; equity: number; benchmark?: number | null }
interface FundData {
  state: { start_capital: number; cash: number; equity: number; pnl_pct: number } | null;
  positions: Pos[]; trades: Trade[]; snapshots: Snap[];
}

const PALETTE = ["#60b4ff", "#2dd4bf", "#a78bfa", "#f97316", "#fbbf24", "#f472b6", "#84cc16", "#38bdf8"];
const ACT: Record<string, { kind: "buy" | "trim" | "rebalance"; label: string }> = {
  buy: { kind: "buy", label: "Koupil" }, trim: { kind: "rebalance", label: "Prodal část" }, sell: { kind: "trim", label: "Prodal" },
};

/** První věta zdůvodnění — začátečníkovi stačí „proč" v jedné větě. */
const firstSentence = (s: string) => (s.match(/^.*?[.!?](\s|$)/)?.[0] ?? s).trim();

// Režim Začátečník — Tradezer investuje: výnos vs. index, co fond drží, poslední tahy lidsky.
export default function InvestorFund() {
  const [d, setD] = useState<FundData | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    fetch("/api/fund", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setD).catch(() => setErr(true));
  }, []);

  if (err) return <Card><p className="text-sm text-amber-300">Fond teď není dostupný.</p></Card>;
  if (!d) return <div className="h-64 animate-pulse rounded-2xl bg-panel" />;
  const s = d.state;
  if (!s) return <Card><p className="text-sm text-gray-400">Fond ještě nezačal obchodovat.</p></Card>;

  const last = d.snapshots[d.snapshots.length - 1];
  const bench = last?.benchmark ? (last.benchmark / s.start_capital - 1) * 100 : null;
  const cashPct = s.equity ? (s.cash / s.equity) * 100 : 0;
  const pos = [...d.positions].sort((a, b) => (b.weight_pct ?? 0) - (a.weight_pct ?? 0));
  const beats = bench != null ? s.pnl_pct >= bench : null;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Bot size={20} className="text-neon" /> Tradezer investuje</h1>
        <p className="mt-1 text-sm text-gray-400">Náš ukázkový fond s virtuálním milionem korun. Řídí se stejnými signály, jaké vidíš v aplikaci — můžeš sledovat, jak by fungovaly v praxi.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Výnos fondu" value={fmtPct(s.pnl_pct)} sub={`hodnota ${fmtCzk(s.equity)}`}
          tone={s.pnl_pct > 0 ? "text-neon" : s.pnl_pct < 0 ? "text-[#ff5050]" : "text-white"} />
        <Stat label="S&P 500 za stejnou dobu" value={bench != null ? fmtPct(bench) : "—"} sub="srovnávací index" />
        <Stat label="Výsledek" value={beats == null ? "—" : beats ? "poráží index" : "zaostává za indexem"}
          sub={bench != null ? `o ${Math.abs(s.pnl_pct - bench).toLocaleString("cs-CZ", { maximumFractionDigits: 1 })} procentního bodu` : undefined}
          tone={beats == null ? "text-white" : beats ? "text-neon" : "text-amber-300"} />
      </div>

      <Card>
        <h2 className="text-[15px] font-bold text-white">Co fond drží</h2>
        <div className="mt-2 flex h-3.5 overflow-hidden rounded-full bg-raised">
          {pos.map((p, i) => <span key={p.symbol} title={`${p.symbol} ${p.weight_pct ?? 0} %`} style={{ width: `${p.weight_pct ?? 0}%`, background: PALETTE[i % PALETTE.length] }} />)}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-gray-300">
          {pos.map((p, i) => (
            <span key={p.symbol} className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
              <b className="text-white">{p.symbol}</b> {(p.weight_pct ?? 0).toLocaleString("cs-CZ", { maximumFractionDigits: 1 })} %
            </span>
          ))}
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-raised ring-1 ring-line-2" /> hotovost {cashPct.toLocaleString("cs-CZ", { maximumFractionDigits: 0 })} %</span>
        </div>
      </Card>

      <Card>
        <h2 className="text-[15px] font-bold text-white">Poslední tahy</h2>
        {d.trades.length === 0 ? <p className="mt-2 text-sm text-gray-500">Zatím žádné obchody.</p> : (
          <ul className="mt-2 divide-y divide-line">
            {d.trades.slice(0, 8).map((t, i) => {
              const a = ACT[t.action] ?? ACT.buy;
              return (
                <li key={i} className="flex items-start gap-3 py-2.5">
                  <div className="w-[96px] shrink-0"><KindPill kind={a.kind} label={a.label} /></div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="font-semibold text-white">{t.symbol}</span>
                      <span className="truncate text-[12px] text-gray-500">{t.name}</span>
                      <span className="ml-auto shrink-0 text-[11.5px] text-gray-600">{new Date(t.ts.slice(0, 10) + "T00:00:00").toLocaleDateString("cs-CZ")}</span>
                    </div>
                    <p className="text-[13px] text-gray-300">{firstSentence(t.reason)}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        <p className="mt-3 text-[11.5px] text-gray-500">Podrobné zdůvodnění, ceny a vývoj hodnoty v grafu najdeš na <Link href="/fond" className="underline hover:text-gray-300">plné stránce fondu</Link>.</p>
      </Card>

      <Disclaimer>Ukázkový fond s virtuálními penězi (paper-trading). Není investiční doporučení; minulá výkonnost nezaručuje budoucí.</Disclaimer>
    </div>
  );
}
