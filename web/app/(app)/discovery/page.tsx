"use client";

import { useEffect, useMemo, useState } from "react";
import { Telescope, Info } from "lucide-react";

interface DItem {
  ticker: string; price: number; chg_pct: number | null;
  ret_5d: number | null; ret_20d: number | null; rel_vol: number | null;
  from_high_pct: number | null; from_low_pct: number | null;
  above_sma20: boolean | null; above_sma50: boolean | null; score: number;
}
interface DData {
  generated: string; universe_size: number; scanned: number; note: string; items: DItem[];
}

type SortKey = "score" | "ret_20d" | "rel_vol";

function pctColor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "#9ca3af";
  return v > 0 ? "#4ade80" : v < 0 ? "#f87171" : "#9ca3af";
}
function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

export default function DiscoveryPage() {
  const [data, setData] = useState<DData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [minRelVol, setMinRelVol] = useState(0);
  const [minRet20, setMinRet20] = useState(0);
  const [onlyAbove, setOnlyAbove] = useState(false);
  const [sort, setSort] = useState<SortKey>("score");

  useEffect(() => {
    fetch("/discovery.json", { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(setData)
      .catch(() => setError("Discovery data nejsou k dispozici. Spusť data/discovery_scan.py."));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    let r = data.items.filter((i) =>
      (i.rel_vol ?? 0) >= minRelVol &&
      (i.ret_20d ?? -999) >= minRet20 &&
      (!onlyAbove || i.above_sma20)
    );
    r = [...r].sort((a, b) => (b[sort] ?? -999) - (a[sort] ?? -999));
    return r;
  }, [data, minRelVol, minRet20, onlyAbove, sort]);

  const chip = (active: boolean) =>
    `rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
      active ? "bg-[#1e2536] text-white border-[#2f3b55]"
        : "bg-[#151823] text-gray-400 border-[#2a2d3a] hover:text-white"}`;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-950/60 border border-blue-900/50">
            <Telescope size={16} className="text-blue-400" />
          </span>
          <h1 className="text-2xl font-bold text-white">Discovery</h1>
        </div>
        <p className="text-sm text-gray-400 mt-1">
          Momentum a neobvyklý objem napříč small/mid-cap univerzem — kandidáti k prozkoumání
        </p>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-yellow-900/40 bg-yellow-950/20 px-3 py-2 text-[11px] text-yellow-300/90">
        <Info size={14} className="mt-0.5 shrink-0" />
        <span><b>Rozcestník, ne rozhodovadlo.</b> Ukazuje, co se hýbe a proč (momentum, relativní objem,
          poloha vůči 52týdennímu high), ne predikci. Krátkodobé momentum je hlučné — ověř si vlastní tezí.
          Není investiční doporučení.</span>
      </div>

      {error && <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">{error}</div>}
      {!data && !error && (
        <div className="h-64 rounded-2xl bg-[#151823] animate-pulse border border-[#2a2d3a]" />
      )}

      {data && (
        <>
          {/* filtry */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider text-gray-500 mr-1">Rel. objem ≥</span>
              {[0, 1, 1.5, 2].map((v) => (
                <button key={v} onClick={() => setMinRelVol(v)} className={chip(minRelVol === v)}>{v === 0 ? "vše" : `${v}×`}</button>
              ))}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider text-gray-500 mr-1">20d momentum ≥</span>
              {[0, 10, 20].map((v) => (
                <button key={v} onClick={() => setMinRet20(v)} className={chip(minRet20 === v)}>{v === 0 ? "vše" : `+${v}%`}</button>
              ))}
            </div>
            <button onClick={() => setOnlyAbove(!onlyAbove)} className={chip(onlyAbove)}>nad SMA20</button>
            <div className="flex items-center gap-1.5 ml-auto">
              <span className="text-[10px] uppercase tracking-wider text-gray-500 mr-1">Řadit</span>
              {(["score", "ret_20d", "rel_vol"] as SortKey[]).map((k) => (
                <button key={k} onClick={() => setSort(k)} className={chip(sort === k)}>
                  {k === "score" ? "Score" : k === "ret_20d" ? "20d" : "Rel. obj."}
                </button>
              ))}
            </div>
          </div>

          <div className="text-xs text-gray-500">
            {rows.length} z {data.scanned} kandidátů · univerzum {data.universe_size} · aktualizováno {new Date(data.generated).toLocaleString("cs")}
          </div>

          <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[760px]">
                <thead>
                  <tr className="text-gray-500 text-[10px] uppercase bg-[#181b26]">
                    <th className="text-left px-3 py-2.5">#</th>
                    <th className="text-left px-3 py-2.5">Ticker</th>
                    <th className="text-right px-3 py-2.5">Cena</th>
                    <th className="text-right px-3 py-2.5">Den</th>
                    <th className="text-right px-3 py-2.5">5d</th>
                    <th className="text-right px-3 py-2.5">20d</th>
                    <th className="text-right px-3 py-2.5">Rel. obj.</th>
                    <th className="text-right px-3 py-2.5">od 52w high</th>
                    <th className="text-left px-3 py-2.5">SMA</th>
                    <th className="text-right px-3 py-2.5">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((i, idx) => (
                    <tr key={i.ticker} className="border-t border-[#232735] hover:bg-[#181b26]/50">
                      <td className="px-3 py-2.5 text-gray-600">{idx + 1}</td>
                      <td className="px-3 py-2.5">
                        <a href={`https://www.tradingview.com/chart/?symbol=${i.ticker}`} target="_blank" rel="noopener noreferrer"
                          className="font-semibold text-gray-100 hover:text-blue-400">{i.ticker}</a>
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-300 font-mono">{i.price}</td>
                      <td className="px-3 py-2.5 text-right font-mono" style={{ color: pctColor(i.chg_pct) }}>{fmtPct(i.chg_pct)}</td>
                      <td className="px-3 py-2.5 text-right font-mono" style={{ color: pctColor(i.ret_5d) }}>{fmtPct(i.ret_5d)}</td>
                      <td className="px-3 py-2.5 text-right font-mono font-semibold" style={{ color: pctColor(i.ret_20d) }}>{fmtPct(i.ret_20d)}</td>
                      <td className="px-3 py-2.5 text-right font-mono" style={{ color: (i.rel_vol ?? 0) >= 1.5 ? "#fbbf24" : "#9ca3af" }}>
                        {i.rel_vol != null ? `${i.rel_vol}×` : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-400">{fmtPct(i.from_high_pct)}</td>
                      <td className="px-3 py-2.5">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded mr-1 ${i.above_sma20 ? "bg-green-950/60 text-green-300" : "bg-[#232735] text-gray-500"}`}>20</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${i.above_sma50 ? "bg-green-950/60 text-green-300" : "bg-[#232735] text-gray-500"}`}>50</span>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <div className="inline-flex items-center gap-2">
                          <div className="w-14 h-1.5 rounded-full bg-[#232735] overflow-hidden">
                            <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.min(100, i.score)}%` }} />
                          </div>
                          <span className="font-mono text-gray-200 w-9 text-right">{i.score}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr><td colSpan={10} className="px-3 py-8 text-center text-gray-500">Žádný kandidát nesplňuje filtry.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
