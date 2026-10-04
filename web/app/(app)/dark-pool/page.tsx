"use client";

import { useEffect, useMemo, useState } from "react";
import { Waves, Info } from "lucide-react";
import { PaywallGuard } from "@/components/PaywallGuard";
import { authHeaders } from "@/lib/auth";

interface DPItem {
  symbol: string; name: string; shares: number; trades: number;
  notional: number; avg_trade: number | null; tier: string | null;
}
interface DPData {
  generated: string | null; week: string | null; count: number;
  universe_size?: number; items: DPItem[]; note?: string; source?: string;
}

function fmtUsd(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}k`;
  return `$${v}`;
}
const fmtNum = (v: number) => v.toLocaleString("cs");

export default function DarkPoolPage() {
  return (
    <PaywallGuard tier="pro" name="Dark Pool">
      <DarkPoolInner />
    </PaywallGuard>
  );
}

function DarkPoolInner() {
  const [data, setData] = useState<DPData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    fetch("/api/darkpool", { cache: "no-store", headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setError("Dark Pool data nejsou k dispozici."));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const n = q.trim().toUpperCase();
    return data.items.filter((i) => !n || i.symbol?.toUpperCase().includes(n) || i.name?.toUpperCase().includes(n));
  }, [data, q]);

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-950/60 border border-indigo-900/50">
            <Waves size={16} className="text-indigo-400" />
          </span>
          <h1 className="text-2xl font-bold text-white">Dark Pool</h1>
        </div>
        <p className="text-sm text-gray-400 mt-1">
          Objemy obchodů mimo burzu (ATS / „dark pools") podle FINRA — kde se institucionálně nejvíc obchodovalo
        </p>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-yellow-900/40 bg-yellow-950/20 px-3 py-2 text-[11px] text-yellow-300/90">
        <Info size={14} className="mt-0.5 shrink-0" />
        <span><b>Rozcestník, ne rozhodovadlo.</b> FINRA OTC Transparency (ATS týdenní objem per symbol) —
          obchody provedené v „dark pools" mimo veřejné burzy. Vysoký objem = silná institucionální aktivita,
          směr (nákup/prodej) data neukazují. <b>Týdenní, s ~měsíčním zpožděním publikace.</b> Není investiční doporučení.</span>
      </div>

      {error && <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">{error}</div>}
      {!data && !error && <div className="h-64 rounded-2xl bg-[#151823] animate-pulse border border-[#2a2d3a]" />}

      {data && (
        <>
          {data.items.length === 0 && (
            <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">
              Zatím žádný snapshot. Spusť <code className="text-yellow-200">py data/finra_darkpool_scan.py --push</code>.
            </div>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hledat ticker / název…"
              className="rounded-md bg-[#151823] border border-[#2a2d3a] px-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-[#2f3b55] w-56" />
            <div className="ml-auto text-xs text-gray-500">
              {rows.length} z {data.count}
              {data.week ? ` · týden ${data.week}` : ""}
              {data.universe_size ? ` · ${fmtNum(data.universe_size)} symbolů v týdnu` : ""}
            </div>
          </div>

          {data.items.length > 0 && (
            <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[720px]">
                  <thead>
                    <tr className="text-gray-500 text-[10px] uppercase bg-[#181b26]">
                      <th className="text-left px-3 py-2.5 w-10">#</th>
                      <th className="text-left px-3 py-2.5">Ticker</th>
                      <th className="text-right px-3 py-2.5">Objem (notional)</th>
                      <th className="text-right px-3 py-2.5">Akcie</th>
                      <th className="text-right px-3 py-2.5">Obchodů</th>
                      <th className="text-right px-3 py-2.5">Ø obchod</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((i, idx) => (
                      <tr key={i.symbol} className="border-t border-[#232735] hover:bg-[#181b26]/50">
                        <td className="px-3 py-2.5 text-gray-600 font-mono text-xs">{idx + 1}</td>
                        <td className="px-3 py-2.5">
                          <a href={`https://www.tradingview.com/chart/?symbol=${i.symbol}`} target="_blank" rel="noopener noreferrer"
                            className="font-semibold text-gray-100 hover:text-indigo-400">{i.symbol}</a>
                          <div className="text-[10px] text-gray-600 truncate max-w-[220px]">{i.name}</div>
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono font-semibold text-indigo-300">{fmtUsd(i.notional)}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-gray-400">{fmtNum(i.shares)}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-gray-400">{fmtNum(i.trades)}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-gray-500">{i.avg_trade ? fmtUsd(i.avg_trade) : "—"}</td>
                      </tr>
                    ))}
                    {rows.length === 0 && (
                      <tr><td colSpan={6} className="px-3 py-8 text-center text-gray-500">Nic nenalezeno.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
