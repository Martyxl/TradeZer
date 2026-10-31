"use client";

import { useEffect, useState } from "react";
import { Coins, PieChart } from "lucide-react";
import { authHeaders } from "@/lib/auth";

interface Payment {
  symbol: string; name: string | null; ex_date: string; per_share: number; quantity: number; currency: string;
  gross: number; gross_base: number | null; status: "announced" | "estimate";
}
interface Share { name: string; value: number; pct: number }
interface Insights {
  base: string; has_meta: boolean;
  dividends: { payments: Payment[]; annual_base: number; yield_pct: number | null; missing_fx: string[] };
  allocation: { total_base: number; sectors: Share[]; countries: Share[]; top_exposure: Share[] };
}

const money = (v: number | null | undefined, ccy: string, d = 0) =>
  v == null ? "—" : `${v.toLocaleString("cs-CZ", { minimumFractionDigits: d, maximumFractionDigits: d })} ${ccy}`;
const COLORS = ["#60ff82", "#60a5fa", "#f59e0b", "#a78bfa", "#f472b6", "#34d399", "#fb923c", "#94a3b8", "#22d3ee", "#e879f9"];
const box = "rounded-xl border border-[#2a2d3a] bg-[#151823] p-4";

function Bars({ rows, ccy }: { rows: Share[]; ccy: string }) {
  return (
    <div className="space-y-1.5">
      {rows.slice(0, 8).map((r, i) => (
        <div key={r.name} className="text-[12px]">
          <div className="flex justify-between gap-2 text-gray-300">
            <span className="truncate" title={r.name}>{r.name}</span>
            <span className="shrink-0 text-gray-400" title={money(r.value, ccy)}>{r.pct.toLocaleString("cs-CZ")} %</span>
          </div>
          <div className="mt-0.5 h-1.5 rounded-full bg-[#0f1117]">
            <div className="h-1.5 rounded-full" style={{ width: `${Math.min(100, r.pct)}%`, background: r.name === "Nezařazeno" ? "#4b5563" : COLORS[i % COLORS.length] }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Očekávané dividendy na 12 měsíců + rozložení portfolia (vč. obsahu ETF). Data: Twelve Data, 1× denně. */
export function PortfolioInsights({ reloadKey }: { reloadKey?: unknown }) {
  const [d, setD] = useState<Insights | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => {
    fetch("/api/investments/insights?base=CZK", { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null)).then(setD).catch(() => setD(null));
  }, [reloadKey]);
  if (!d || !d.has_meta) return null;
  const pays = d.dividends.payments;
  const shown = all ? pays : pays.slice(0, 6);
  const al = d.allocation;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className={box}>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-white"><Coins size={15} className="text-[#f59e0b]" /> Dividendy na příštích 12 měsíců</div>
        {pays.length === 0 ? (
          <p className="text-[12px] text-gray-500">Žádný z držených titulů podle dosavadní historie dividendu nevyplácí.</p>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-baseline gap-x-3">
              <span className="text-xl font-bold text-white">≈ {money(d.dividends.annual_base, d.base)}</span>
              <span className="text-[12px] text-gray-400">hrubého ročně{d.dividends.yield_pct != null ? ` · ${d.dividends.yield_pct.toLocaleString("cs-CZ")} % z hodnoty portfolia` : ""}</span>
            </div>
            <table className="w-full text-[12px]">
              <tbody>
                {shown.map((p, i) => (
                  <tr key={i} className="border-t border-[#20242f]">
                    <td className="py-1.5 text-gray-400">{new Date(p.ex_date).toLocaleDateString("cs-CZ", { day: "numeric", month: "numeric", year: "2-digit" })}</td>
                    <td className="py-1.5"><span className="font-medium text-white">{p.symbol}</span>
                      <span className={`ml-1.5 rounded px-1 py-0.5 text-[10px] ${p.status === "announced" ? "bg-[#14532d55] text-[#86efac]" : "bg-[#1e2536] text-gray-400"}`}>
                        {p.status === "announced" ? "vyhlášeno" : "odhad"}
                      </span>
                    </td>
                    <td className="py-1.5 text-right text-gray-400">{p.per_share.toLocaleString("cs-CZ", { maximumFractionDigits: 4 })} {p.currency} × {p.quantity.toLocaleString("cs-CZ", { maximumFractionDigits: 4 })}</td>
                    <td className="py-1.5 text-right text-gray-200">{p.gross_base != null ? money(p.gross_base, d.base) : money(p.gross, p.currency, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {pays.length > 6 && (
              <button onClick={() => setAll((a) => !a)} className="mt-2 text-[12px] text-blue-400 hover:text-blue-300">
                {all ? "Zobrazit méně" : `Všechny výplaty (${pays.length})`}
              </button>
            )}
          </>
        )}
        <p className="mt-3 text-[10px] leading-relaxed text-gray-600">
          Datum = rozhodný den (ex-date): akcii musíš držet den předtím. „Odhad“ = další výplata podle dosavadní frekvence a poslední
          částky; firma ji může změnit nebo zrušit. Částky jsou hrubé — u US akcií se srazí 15 % (s W-8BEN) a v ČR se dividenda daní,
          viz <a href="/dane" className="text-gray-500 underline">Daně</a>.
        </p>
      </div>

      <div className={box}>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-white"><PieChart size={15} className="text-[#60a5fa]" /> Rozložení portfolia</div>
        {al.total_base ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <div><div className="mb-1.5 text-[10px] uppercase tracking-wider text-gray-500">Sektory</div><Bars rows={al.sectors} ccy={d.base} /></div>
              <div><div className="mb-1.5 text-[10px] uppercase tracking-wider text-gray-500">Země</div><Bars rows={al.countries} ccy={d.base} /></div>
            </div>
            {al.top_exposure.length > 0 && (
              <div className="mt-4">
                <div className="mb-1.5 text-[10px] uppercase tracking-wider text-gray-500">Největší skutečné pozice (vč. firem uvnitř ETF)</div>
                <div className="flex flex-wrap gap-1.5">
                  {al.top_exposure.map((r) => (
                    <span key={r.name} className="rounded bg-[#0f1117] px-2 py-1 text-[11px] text-gray-300" title={money(r.value, d.base)}>
                      {r.name} <span className="text-gray-500">{r.pct.toLocaleString("cs-CZ")} %</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
            <p className="mt-3 text-[10px] leading-relaxed text-gray-600">ETF jsou rozpuštěné podle svého obsahu — vidíš, kam jsou tvoje peníze skutečně investované. Data: Twelve Data, obnova 1× denně.</p>
          </>
        ) : (
          <p className="text-[12px] text-gray-500">Rozložení se ukáže, až budou známé aktuální ceny pozic.</p>
        )}
      </div>
    </div>
  );
}
