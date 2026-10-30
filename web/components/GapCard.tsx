"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, CheckCircle2, ChevronDown } from "lucide-react";

interface Agg { n: number; fill_pct: number | null; fill_ci: [number, number] | null; cont_pct: number | null; cont_ci: [number, number] | null }
interface Row extends Agg { lo: number; hi: number | null; up: Agg; down: Agg }
interface Gap {
  ticker: string; etf: string; prev_date: string; prev_close: number;
  status: "premarket" | "open" | "closed_today" | "closed";
  price?: number; last?: number; gap_pct?: number; direction?: "up" | "down";
  bucket?: { lo: number; hi: number | null; all: Agg } & Agg;
  filled_today?: boolean | null; fut_symbol?: string; fut_target?: number | null;
  table: { n_days: number; since: string | null; rows: Row[] };
}

const STATUS: Record<Gap["status"], string> = {
  premarket: "premarket · odhad z aktuální ceny",
  open: "po openu · gap z ceny v 9:30",
  closed_today: "dnešní session skončila",
  closed: "trh zavřený",
};
const cz = (n: number) => n.toLocaleString("cs-CZ");
const range = (lo: number, hi: number | null) => (hi == null ? `nad ${cz(lo)} %` : lo === 0 ? `do ${cz(hi)} %` : `${cz(lo)}–${cz(hi)} %`);
const fmt = (n: number, d = 2) => n.toLocaleString("cs-CZ", { minimumFractionDigits: d, maximumFractionDigits: d });
const ci = (c: [number, number] | null) => (c ? ` (${c[0]}–${c[1]} %)` : "");

/** Gap před openem + historická pravděpodobnost, že se cena během dne vrátí na včerejší close. */
export function GapCard({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Gap | null>(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    fetch(`/api/bias/gap?ticker=${ticker}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setD(j))
      .catch(() => {});
  }, [ticker]);

  useEffect(() => { setD(null); load(); }, [load]);
  // Premarket / během session obnovuj (gap se do 9:30 mění, po openu sledujeme zavření)
  useEffect(() => {
    if (!d || (d.status !== "premarket" && d.status !== "open")) return;
    const id = setInterval(() => { if (document.visibilityState === "visible") load(); }, 120_000);
    return () => clearInterval(id);
  }, [d, load]);

  if (!d) return null;
  const has = d.gap_pct != null && d.bucket;
  const down = d.direction === "down";
  const color = down ? "#f87171" : "#4ade80";
  const b = d.bucket;
  const fillColor = (p: number | null) => (p == null ? "#9ca3af" : p >= 65 ? "#4ade80" : p >= 40 ? "#eab308" : "#fb923c");

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4">
      <div className="flex flex-wrap items-center gap-2">
        {down ? <ArrowDownRight size={15} className="text-red-400" /> : <ArrowUpRight size={15} className="text-green-400" />}
        <h2 className="text-sm font-semibold text-white">Gap před openem · {d.etf} ≈ {d.ticker}</h2>
        <span className="text-[10px] text-gray-500">{STATUS[d.status]}</span>
      </div>

      {has && b ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-[auto,1fr] sm:items-center">
          <div>
            <div className="text-2xl font-bold" style={{ color }}>{d.gap_pct! > 0 ? "+" : ""}{fmt(d.gap_pct!)} %</div>
            <div className="text-[11px] text-gray-500">
              {d.etf} {fmt(d.price!)} vs close {fmt(d.prev_close)} ({new Date(`${d.prev_date}T12:00:00`).toLocaleDateString("cs-CZ")})
            </div>
          </div>
          <div className="rounded-lg border border-[#232735] bg-[#151823] px-3 py-2 text-[12px] text-gray-300 space-y-1">
            {d.filled_today ? (
              <div className="flex items-center gap-1.5 font-semibold text-green-400"><CheckCircle2 size={13} /> Gap se dnes už zavřel (cena se vrátila na včerejší close).</div>
            ) : (
              <div>
                Gap {down ? "dolů" : "nahoru"} {range(b.lo, b.hi)} se historicky během NY session zavřel v{" "}
                <span className="font-bold" style={{ color: fillColor(b.fill_pct) }}>{b.fill_pct} %</span> dní
                <span className="text-gray-500">{ci(b.fill_ci)} · n={b.n}</span>.
              </div>
            )}
            <div>
              Cíl zavření: <span className="font-semibold text-white">{d.etf} {fmt(d.prev_close)}</span>
              {d.fut_target != null && <> ≈ <span className="font-semibold text-white">{d.fut_symbol} {fmt(d.fut_target, 2)}</span> <span className="text-gray-500">(close v 16:00 ET)</span></>}
            </div>
            <div className="text-[11px] text-gray-500">
              Směr dne gap nepředpovídá: ve směru gapu skončilo {b.cont_pct} %{ci(b.cont_ci)} dní — prakticky hod mincí.
            </div>
          </div>
        </div>
      ) : (
        <p className="mt-2 text-[12px] text-gray-500">Dnes zatím žádný gap ({d.status === "closed" ? "trh je zavřený" : "chybí data"}). Včerejší close {d.etf} {fmt(d.prev_close)}.</p>
      )}

      <button onClick={() => setOpen((o) => !o)} className="mt-3 flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300">
        <ChevronDown size={13} className={open ? "rotate-180" : ""} /> Tabulka podle velikosti gapu ({d.etf}, {d.table.n_days} dní od {d.table.since?.slice(0, 4)})
      </button>
      {open && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[520px] text-xs">
            <thead>
              <tr className="text-[10px] uppercase text-gray-500">
                <th className="pb-2 text-left">Velikost gapu</th>
                <th className="pb-2 text-right">n (↑ / ↓)</th>
                <th className="pb-2 text-right">Gap se zavře (↑ / ↓)</th>
                <th className="pb-2 text-right">Den ve směru gapu</th>
              </tr>
            </thead>
            <tbody>
              {d.table.rows.map((r) => {
                const hit = b && r.lo === b.lo;
                return (
                  <tr key={r.lo} className={`border-t border-[#232735] ${hit ? "bg-blue-950/30" : ""}`}>
                    <td className="py-1.5 text-gray-200">{range(r.lo, r.hi)}{hit && <span className="ml-1.5 rounded bg-blue-600 px-1 text-[9px] font-semibold text-white">DNES</span>}</td>
                    <td className="text-right text-gray-400">{r.n} ({r.up.n} / {r.down.n})</td>
                    <td className="text-right">
                      <span className="font-semibold" style={{ color: fillColor(r.fill_pct) }}>{r.fill_pct ?? "—"} %</span>
                      <span className="text-gray-500"> ({r.up.fill_pct ?? "—"} / {r.down.fill_pct ?? "—"})</span>
                    </td>
                    <td className="text-right text-gray-400">{r.cont_pct ?? "—"} %{ci(r.cont_ci)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-[10px] text-gray-500">
            Gap = open 9:30 ET proti close předchozího dne (16:00 ET), měřeno na {d.etf} (proxy pro {d.ticker}). „Zavře“ = cena se během NY session aspoň jednou
            dotkla včerejšího close. Historická statistika, ne investiční doporučení.
          </p>
        </div>
      )}
    </div>
  );
}
