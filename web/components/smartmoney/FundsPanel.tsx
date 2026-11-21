"use client";

import { useEffect, useMemo, useState } from "react";
import { Info, Search, TrendingDown, TrendingUp, Flag, ChevronDown } from "lucide-react";
import { authHeaders } from "@/lib/auth";

/** [klíč fondu, akce, váha %, změna kusů %] */
type FundMove = [string, "new" | "added" | "reduced" | "sold", number, number | null];
interface Consensus {
  ticker: string | null; name: string; holders: number; funds: FundMove[]; count: number;
  new?: number; exits?: number; flow: number;
}
interface Pos {
  ticker: string | null; name: string; value: number; weight: number; prev_weight?: number;
  action?: string; chg_pct: number | null; flow?: number;
}
interface Fund {
  key: string; name: string; manager: string; style: string; cik: number; period: string | null;
  filed: string | null; prev_period: string | null; stale: boolean; total_value: number; positions: number;
  top: Pos[]; changes: Record<"new" | "added" | "reduced" | "sold", Pos[]>;
}
interface Stake {
  date: string; form: string; fund: string; fund_name: string; ticker: string | null; issuer: string;
  percent: number | null; activist: boolean; amendment: boolean; url: string;
}
interface TickerInfo { n: string; h: [string, number][]; hc: number; b: FundMove[]; s: FundMove[] }
export interface FundsData {
  generated: string | null; quarter: string | null; note?: string;
  fund_names: Record<string, string>; funds: Fund[];
  consensus_buys: Consensus[]; consensus_sells: Consensus[];
  most_held: { ticker: string | null; name: string; holders: number; funds: [string, number][]; value: number }[];
  stakes: Stake[]; by_ticker: Record<string, TickerInfo>;
}

const ACTION: Record<string, { label: string; cls: string }> = {
  new: { label: "nová", cls: "bg-emerald-900/60 text-emerald-200" },
  added: { label: "navýšil", cls: "bg-emerald-950/60 text-emerald-300" },
  reduced: { label: "snížil", cls: "bg-red-950/50 text-red-300" },
  sold: { label: "prodal vše", cls: "bg-red-900/50 text-red-200" },
};

export function fmtUsd(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}k`;
  return `$${Math.round(v)}`;
}

function quarterLabel(p: string | null): string {
  if (!p) return "—";
  const [y, m] = p.split("-").map(Number);
  return `Q${Math.ceil(m / 3)} ${y}`;
}

function Ticker({ t, name }: { t: string | null; name: string }) {
  return (
    <div className="min-w-0">
      {t ? (
        <a href={`https://www.tradingview.com/chart/?symbol=${t}`} target="_blank" rel="noopener noreferrer"
          className="font-semibold text-gray-100 hover:text-emerald-400">{t}</a>
      ) : <span className="font-semibold text-gray-300">—</span>}
      <div className="text-[10px] text-gray-500 truncate max-w-[180px]" title={name}>{name}</div>
    </div>
  );
}

function MoveChip({ m, names }: { m: FundMove; names: Record<string, string> }) {
  const a = ACTION[m[1]];
  const chg = m[1] === "added" || m[1] === "reduced" ? ` ${m[3]! > 0 ? "+" : ""}${Math.round(m[3] ?? 0)} %` : "";
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${a.cls}`}
      title={`${names[m[0]] ?? m[0]}: ${a.label}${chg}, ${m[2]} % portfolia`}>
      {names[m[0]] ?? m[0]}
      <span className="opacity-70">{m[1] === "new" ? "nová" : m[1] === "sold" ? "ven" : chg.trim()}</span>
    </span>
  );
}

function ConsensusList({ title, rows, names, buy }: {
  title: string; rows: Consensus[]; names: Record<string, string>; buy: boolean;
}) {
  const [more, setMore] = useState(false);
  const shown = more ? rows : rows.slice(0, 12);
  const Icon = buy ? TrendingUp : TrendingDown;
  return (
    <div className="rounded-xl border border-line bg-panel-2 overflow-hidden">
      <div className={`flex items-center gap-2 px-3 py-2.5 border-b border-line text-sm font-semibold ${buy ? "text-emerald-300" : "text-red-300"}`}>
        <Icon size={15} /> {title}
      </div>
      {rows.length === 0 && <div className="px-3 py-6 text-center text-xs text-gray-500">Žádná shoda mezi fondy.</div>}
      <div className="divide-y divide-line">
        {shown.map((r) => (
          <div key={(r.ticker ?? "") + r.name} className="px-3 py-2.5">
            <div className="flex items-start gap-3">
              <Ticker t={r.ticker} name={r.name} />
              <div className="ml-auto text-right shrink-0">
                <div className={`text-sm font-semibold ${buy ? "text-emerald-300" : "text-red-300"}`}>
                  {r.count} {r.count === 1 ? "fond" : r.count < 5 ? "fondy" : "fondů"}
                </div>
                <div className="text-[10px] text-gray-500">
                  {buy ? (r.new ? `${r.new}× nová · ` : "") : (r.exits ? `${r.exits}× ven · ` : "")}
                  {fmtUsd(r.flow)}
                </div>
              </div>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1">
              {r.funds.map((m) => <MoveChip key={m[0]} m={m} names={names} />)}
            </div>
          </div>
        ))}
      </div>
      {rows.length > 12 && (
        <button onClick={() => setMore(!more)} className="w-full border-t border-line py-2 text-[11px] text-gray-400 hover:text-white">
          {more ? "Méně" : `Dalších ${rows.length - 12}`}
        </button>
      )}
    </div>
  );
}

function TickerLookup({ data }: { data: FundsData }) {
  const [q, setQ] = useState("");
  const t = q.trim().toUpperCase();
  const info = t ? data.by_ticker[t] : undefined;
  const names = data.fund_names;
  return (
    <div className="rounded-xl border border-line bg-panel-2 p-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ticker, např. NVDA"
            className="rounded-md bg-panel border border-line pl-8 pr-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-line-2 w-48 uppercase" />
        </div>
        <span className="text-xs text-gray-500">Které z vybraných fondů akcii drží, kupují nebo prodávají</span>
      </div>
      {t && !info && <div className="mt-3 text-xs text-gray-500">{t} nedrží žádný ze sledovaných fondů.</div>}
      {info && (
        <div className="mt-3 space-y-2 text-xs">
          <div className="text-gray-300"><b className="text-white">{t}</b> · {info.n} · drží {info.hc} {info.hc === 1 ? "fond" : info.hc < 5 ? "fondy" : "fondů"}</div>
          {info.b.length > 0 && (
            <div className="flex flex-wrap items-center gap-1"><span className="text-emerald-400 mr-1">Kupují:</span>
              {info.b.map((m) => <MoveChip key={m[0]} m={m} names={names} />)}</div>
          )}
          {info.s.length > 0 && (
            <div className="flex flex-wrap items-center gap-1"><span className="text-red-400 mr-1">Prodávají:</span>
              {info.s.map((m) => <MoveChip key={m[0]} m={m} names={names} />)}</div>
          )}
          <div className="flex flex-wrap items-center gap-1"><span className="text-gray-500 mr-1">Drží:</span>
            {info.h.map(([k, w]) => (
              <span key={k} className="rounded bg-panel px-1.5 py-0.5 text-[10px] text-gray-300 border border-line">
                {names[k] ?? k} <span className="text-gray-500">{w} %</span>
              </span>
            ))}
            {info.hc > info.h.length && <span className="text-[10px] text-gray-500">+{info.hc - info.h.length}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

function StakesTable({ rows }: { rows: Stake[] }) {
  const [only, setOnly] = useState<"all" | "13d">("all");
  const shown = rows.filter((s) => only === "all" || s.activist).slice(0, 40);
  return (
    <div className="rounded-xl border border-line bg-panel-2 overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2.5 border-b border-line">
        <Flag size={14} className="text-amber-400" />
        <span className="text-sm font-semibold text-gray-100">Podíly nad 5 % (13D / 13G)</span>
        <span className="text-[11px] text-gray-500">hlášení do 10 dnů — nejčerstvější signál od fondů</span>
        <div className="ml-auto flex gap-1">
          {(["all", "13d"] as const).map((k) => (
            <button key={k} onClick={() => setOnly(k)}
              className={`rounded px-2 py-0.5 text-[11px] border ${only === k ? "bg-raised text-white border-line-2" : "text-gray-400 border-line hover:text-white"}`}>
              {k === "all" ? "Vše" : "Jen 13D (aktivní)"}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead>
            <tr className="text-gray-500 text-[10px] uppercase">
              <th className="text-left px-3 py-2">Podáno</th><th className="text-left px-3 py-2">Fond</th>
              <th className="text-left px-3 py-2">Firma</th><th className="text-left px-3 py-2">Typ</th>
              <th className="text-right px-3 py-2">Podíl</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((s, i) => (
              <tr key={i} className="border-t border-line">
                <td className="px-3 py-2 font-mono text-xs text-gray-400 whitespace-nowrap">{s.date}</td>
                <td className="px-3 py-2 text-gray-200">{s.fund_name}</td>
                <td className="px-3 py-2"><Ticker t={s.ticker} name={s.issuer} /></td>
                <td className="px-3 py-2">
                  <a href={s.url} target="_blank" rel="noopener noreferrer"
                    className={`text-[10px] px-1.5 py-0.5 rounded ${s.activist ? "bg-amber-950/60 text-amber-300" : "bg-panel text-gray-300 border border-line"}`}>
                    {s.activist ? "13D aktivní" : "13G pasivní"}{s.amendment ? " · dodatek" : ""}
                  </a>
                </td>
                <td className="px-3 py-2 text-right font-mono text-gray-200">{s.percent != null ? `${s.percent} %` : "—"}</td>
              </tr>
            ))}
            {shown.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-xs text-gray-500">Za poslední 4 měsíce nic.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FundCard({ f }: { f: Fund }) {
  const [open, setOpen] = useState(false);
  const n = open ? 8 : 3;
  return (
    <div className={`rounded-xl border bg-panel-2 p-3 ${f.stale ? "border-line opacity-70" : "border-line"}`}>
      <div className="flex items-start gap-2">
        <div className="min-w-0">
          <div className="font-semibold text-gray-100 truncate">{f.name}</div>
          <div className="text-[11px] text-gray-500 truncate">{f.manager} · {f.style}</div>
        </div>
        <div className="ml-auto text-right shrink-0">
          <div className="font-mono text-sm text-gray-200">{fmtUsd(f.total_value)}</div>
          <div className="text-[10px] text-gray-500">{f.positions} pozic · {quarterLabel(f.period)}</div>
        </div>
      </div>
      {f.stale && <div className="mt-1 text-[10px] text-amber-400">Poslední výpis je starší — do konsenzu se nepočítá.</div>}
      <div className="mt-2.5 space-y-1">
        {f.top.slice(0, open ? 10 : 5).map((p) => (
          <div key={(p.ticker ?? "") + p.name} className="flex items-center gap-2 text-xs">
            <span className="w-14 shrink-0 font-semibold text-gray-200 truncate" title={p.name}>{p.ticker ?? p.name.slice(0, 8)}</span>
            <div className="h-1.5 flex-1 rounded bg-panel overflow-hidden">
              <div className="h-full rounded bg-emerald-600/70" style={{ width: `${Math.min(100, p.weight * 2)}%` }} />
            </div>
            <span className="w-12 text-right font-mono text-gray-400">{p.weight.toFixed(1)} %</span>
          </div>
        ))}
      </div>
      {f.prev_period && (
        <div className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
          {(["new", "added", "reduced", "sold"] as const).map((a) => (
            <div key={a} className="min-w-0">
              <div className="text-[10px] uppercase tracking-wide text-gray-500">{ACTION[a].label}</div>
              <div className={`truncate ${a === "new" || a === "added" ? "text-emerald-300" : "text-red-300"}`}>
                {f.changes[a].length === 0 ? <span className="text-gray-600">—</span> :
                  f.changes[a].slice(0, n).map((p) => p.ticker ?? p.name.slice(0, 10)).join(", ")}
              </div>
            </div>
          ))}
        </div>
      )}
      <button onClick={() => setOpen(!open)} className="mt-2 flex items-center gap-1 text-[11px] text-gray-500 hover:text-white">
        <ChevronDown size={12} className={open ? "rotate-180" : ""} /> {open ? "Méně" : "Víc pozic a změn"}
      </button>
    </div>
  );
}

export function FundsPanel() {
  const [data, setData] = useState<FundsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [style, setStyle] = useState("all");

  useEffect(() => {
    fetch("/api/smart-money/funds", { cache: "no-store", headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setError("Data fondů nejsou k dispozici."));
  }, []);

  const styles = useMemo(() => Array.from(new Set((data?.funds ?? []).map((f) => f.style))), [data]);
  const funds = (data?.funds ?? []).filter((f) => style === "all" || f.style === style);

  if (error) return <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">{error}</div>;
  if (!data) return <div className="h-64 rounded-2xl bg-panel-2 animate-pulse border border-line" />;
  if (data.funds.length === 0)
    return <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">{data.note}</div>;

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-2 rounded-lg border border-yellow-900/40 bg-yellow-950/20 px-3 py-2 text-[11px] text-yellow-300/90">
        <Info size={14} className="mt-0.5 shrink-0" />
        <span><b>Konfluence, ne časování.</b> Čtvrtletní výpisy SEC 13F ({data.funds.length} vybraných fondů,
          poslední čtvrtletí {quarterLabel(data.quarter)}) ukazují stav ke konci čtvrtletí a vycházejí až do 45 dnů
          poté — fond mohl mezitím prodat. Jen dlouhé pozice v US akciích, bez shortů a opcí. Do konsenzu se počítá
          jen pozice od 0,5 % portfolia fondu. Není investiční doporučení.</span>
      </div>

      <TickerLookup data={data} />

      <div className="grid gap-4 lg:grid-cols-2">
        <ConsensusList title={`Fondy nakupují (${quarterLabel(data.quarter)})`} rows={data.consensus_buys} names={data.fund_names} buy />
        <ConsensusList title={`Fondy prodávají (${quarterLabel(data.quarter)})`} rows={data.consensus_sells} names={data.fund_names} buy={false} />
      </div>

      <StakesTable rows={data.stakes} />

      {data.most_held.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Nejčastěji držené mezi sledovanými fondy</div>
          <div className="flex flex-wrap gap-2">
            {data.most_held.map((m) => (
              <div key={(m.ticker ?? "") + m.name} className="rounded-lg border border-line bg-panel-2 px-3 py-1.5"
                title={m.funds.map(([k, w]) => `${data.fund_names[k] ?? k} ${w} %`).join("\n")}>
                <span className="font-semibold text-gray-100">{m.ticker ?? m.name}</span>
                <span className="ml-2 text-xs text-gray-400">{m.holders} fondů</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <span className="mr-2 text-[10px] uppercase tracking-wider text-gray-500">Fondy</span>
          {["all", ...styles].map((s) => (
            <button key={s} onClick={() => setStyle(s)}
              className={`rounded-md px-2.5 py-0.5 text-[11px] border ${style === s ? "bg-raised text-white border-line-2" : "bg-panel-2 text-gray-400 border-line hover:text-white"}`}>
              {s === "all" ? "Vše" : s}
            </button>
          ))}
          {data.generated && <span className="ml-auto text-[11px] text-gray-500">aktualizováno {new Date(data.generated).toLocaleString("cs")}</span>}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {funds.map((f) => <FundCard key={f.key} f={f} />)}
        </div>
      </div>
    </div>
  );
}
