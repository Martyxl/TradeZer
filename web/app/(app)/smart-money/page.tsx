"use client";

import { useEffect, useMemo, useState } from "react";
import { Landmark, Info } from "lucide-react";

interface Insider {
  date: string; person: string; role: string; ticker: string; issuer: string;
  tx: "buy" | "sell"; shares: number; price: number; value: number;
}
interface TopBuy {
  ticker: string; issuer: string; buys: number; sells: number;
  buy_value: number; sell_value: number;
}
interface SMData {
  generated: string | null; count: number; buys: number; sells: number;
  note?: string; top_buys: TopBuy[]; insiders: Insider[]; congress: unknown[];
}

type TxFilter = "all" | "buy" | "sell";

function fmtUsd(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}k`;
  return `$${v}`;
}
function fmtNum(v: number): string {
  return v.toLocaleString("cs");
}

export default function SmartMoneyPage() {
  const [data, setData] = useState<SMData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tx, setTx] = useState<TxFilter>("all");
  const [q, setQ] = useState("");

  useEffect(() => {
    fetch("/api/smart-money", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setError("Smart Money data nejsou k dispozici."));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toUpperCase();
    return data.insiders.filter((i) =>
      (tx === "all" || i.tx === tx) &&
      (!needle || i.ticker.includes(needle) || i.person.toUpperCase().includes(needle))
    );
  }, [data, tx, q]);

  const chip = (active: boolean) =>
    `rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
      active ? "bg-[#1e2536] text-white border-[#2f3b55]"
        : "bg-[#151823] text-gray-400 border-[#2a2d3a] hover:text-white"}`;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-950/60 border border-emerald-900/50">
            <Landmark size={16} className="text-emerald-400" />
          </span>
          <h1 className="text-2xl font-bold text-white">Smart Money</h1>
        </div>
        <p className="text-sm text-gray-400 mt-1">
          Insider obchody (SEC Form 4) — kdo z vedení firem nakupoval a prodával vlastní akcie
        </p>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-yellow-900/40 bg-yellow-950/20 px-3 py-2 text-[11px] text-yellow-300/90">
        <Info size={14} className="mt-0.5 shrink-0" />
        <span><b>Rozcestník, ne rozhodovadlo.</b> Veřejná regulatorní hlášení (SEC Form 4) —
          open-market nákup (P) a prodej (S). Insideři prodávají z mnoha důvodů (daně, diverzifikace),
          <b> nákupy mají obvykle vyšší signál</b>. Data se zpožďují (hlášení do 2 dnů). Není investiční doporučení.</span>
      </div>

      {error && <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">{error}</div>}
      {!data && !error && <div className="h-64 rounded-2xl bg-[#151823] animate-pulse border border-[#2a2d3a]" />}

      {data && (
        <>
          {data.insiders.length === 0 && (
            <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">
              Zatím žádný snapshot. Spusť <code className="text-yellow-200">py data/smart_money_scan.py --push</code>.
            </div>
          )}

          {/* Top nákupy podle hodnoty */}
          {data.top_buys.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">
                Top nákupy podle hodnoty (agregováno za okno)
              </div>
              <div className="flex flex-wrap gap-2">
                {data.top_buys.map((t) => (
                  <div key={t.ticker} className="rounded-lg border border-emerald-900/40 bg-emerald-950/20 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-100">{t.ticker}</span>
                      <span className="font-mono text-emerald-400 text-sm">{fmtUsd(t.buy_value)}</span>
                    </div>
                    <div className="text-[10px] text-gray-500">{t.buys}× nákup{t.sells ? ` · ${t.sells}× prodej` : ""}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* filtry */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
            <div className="flex items-center gap-1.5">
              {(["all", "buy", "sell"] as TxFilter[]).map((k) => (
                <button key={k} onClick={() => setTx(k)} className={chip(tx === k)}>
                  {k === "all" ? "Vše" : k === "buy" ? "Nákupy" : "Prodeje"}
                </button>
              ))}
            </div>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Hledat ticker / jméno…"
              className="rounded-md bg-[#151823] border border-[#2a2d3a] px-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-[#2f3b55] w-56"
            />
            <div className="ml-auto text-xs text-gray-500">
              {rows.length} z {data.count} · {data.buys} nákupů / {data.sells} prodejů
              {data.generated ? ` · ${new Date(data.generated).toLocaleString("cs")}` : ""}
            </div>
          </div>

          <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[820px]">
                <thead>
                  <tr className="text-gray-500 text-[10px] uppercase bg-[#181b26]">
                    <th className="text-left px-3 py-2.5">Datum</th>
                    <th className="text-left px-3 py-2.5">Insider</th>
                    <th className="text-left px-3 py-2.5">Ticker</th>
                    <th className="text-center px-3 py-2.5">Typ</th>
                    <th className="text-right px-3 py-2.5">Akcií</th>
                    <th className="text-right px-3 py-2.5">Cena</th>
                    <th className="text-right px-3 py-2.5">Hodnota</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((i, idx) => (
                    <tr key={idx} className="border-t border-[#232735] hover:bg-[#181b26]/50">
                      <td className="px-3 py-2.5 text-gray-400 font-mono text-xs whitespace-nowrap">{i.date}</td>
                      <td className="px-3 py-2.5">
                        <div className="text-gray-200">{i.person}</div>
                        <div className="text-[10px] text-gray-500">{i.role}</div>
                      </td>
                      <td className="px-3 py-2.5">
                        <a href={`https://www.tradingview.com/chart/?symbol=${i.ticker}`} target="_blank" rel="noopener noreferrer"
                          className="font-semibold text-gray-100 hover:text-emerald-400">{i.ticker}</a>
                        <div className="text-[10px] text-gray-600 truncate max-w-[160px]">{i.issuer}</div>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                          i.tx === "buy" ? "bg-emerald-950/60 text-emerald-300" : "bg-red-950/50 text-red-300"}`}>
                          {i.tx === "buy" ? "Nákup" : "Prodej"}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-300">{fmtNum(i.shares)}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-400">{i.price ? `$${i.price}` : "—"}</td>
                      <td className="px-3 py-2.5 text-right font-mono font-semibold"
                        style={{ color: i.tx === "buy" ? "#4ade80" : "#f87171" }}>
                        {i.value ? fmtUsd(i.value) : "—"}
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && data.insiders.length > 0 && (
                    <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-500">Žádný záznam nesplňuje filtry.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-lg border border-[#2a2d3a] bg-[#151823] px-3 py-2 text-[11px] text-gray-500">
            <b className="text-gray-400">Congress obchody</b> (Senate/House) — připravuje se. Volné mirrory
            mezitím zmizely; hledá se spolehlivý free zdroj.
          </div>
        </>
      )}
    </div>
  );
}
