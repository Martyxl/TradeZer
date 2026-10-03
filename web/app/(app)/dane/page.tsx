"use client";

import { useEffect, useState } from "react";
import { Receipt, CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { useAuth, authHeaders } from "@/lib/auth";

interface Lot {
  symbol: string; name: string | null; quantity: number; buy_date: string;
  free_date: string; days_remaining: number; tax_free: boolean;
  currency: string; cost: number; value: number | null;
}
interface TimeTest {
  base: string; years: number; today: string; lots: Lot[]; upcoming_12m: Lot[];
  summary: { value_tax_free: number; value_pending: number; complete: boolean; n_tax_free: number; n_pending: number };
}

const fmt = (n: number | null | undefined, ccy = "") =>
  n === null || n === undefined ? "—" : `${n.toLocaleString("cs-CZ", { maximumFractionDigits: 0 })}${ccy ? " " + ccy : ""}`;
const dCZ = (iso: string) => new Date(iso).toLocaleDateString("cs-CZ");

function remainLabel(days: number): string {
  if (days <= 0) return "osvobozeno";
  if (days < 60) return `za ${days} dní`;
  const m = Math.round(days / 30.4);
  if (m < 24) return `za ~${m} měs.`;
  return `za ~${(days / 365).toFixed(1)} r.`;
}

export default function DanePage() {
  const { user, loading: authLoading } = useAuth();
  const [tt, setTt] = useState<TimeTest | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    fetch("/api/investments/timetest?base=CZK", { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then(setTt)
      .finally(() => setLoading(false));
  }, [user]);

  if (authLoading) return <div className="h-40 animate-pulse rounded-xl bg-[#1a1d27]" />;
  if (!user)
    return <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-8 text-center text-gray-400">
      Pro daňový test se <a href="/prihlaseni" className="text-[#60ff82] underline">přihlas</a>.</div>;

  const s = tt?.summary;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
          <Receipt size={20} className="text-[#60ff82]" /> Daňový časový test
        </h1>
        <p className="mt-1 text-sm text-gray-400">
          Cenné papíry držené <strong>déle než 3 roky</strong> → zisk z prodeje je v ČR osvobozen od daně z příjmu.
          Tady vidíš, odkdy můžeš jednotlivé nákupy prodat bez daně.
        </p>
      </div>

      {/* Souhrn */}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-[rgba(96,255,130,0.3)] bg-[#0c1a11] p-4">
          <div className="flex items-center gap-1.5 text-[11px] uppercase text-[#8fffab]"><CheckCircle2 size={13} /> Osvobozeno (přes 3 roky)</div>
          <div className="mt-1 text-xl font-bold text-white">{fmt(s?.value_tax_free, "CZK")}</div>
          <div className="text-xs text-gray-500">{s?.n_tax_free ?? 0} nákupních pozic</div>
        </div>
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.05] p-4">
          <div className="flex items-center gap-1.5 text-[11px] uppercase text-amber-300"><Clock size={13} /> Zatím v testu (do 3 let)</div>
          <div className="mt-1 text-xl font-bold text-white">{fmt(s?.value_pending, "CZK")}</div>
          <div className="text-xs text-gray-500">{s?.n_pending ?? 0} nákupních pozic</div>
        </div>
        <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
          <div className="text-[11px] uppercase text-gray-500">Nejbližší osvobození</div>
          {tt?.upcoming_12m.length ? (
            <>
              <div className="mt-1 text-xl font-bold text-white">{dCZ(tt.upcoming_12m[0].free_date)}</div>
              <div className="text-xs text-gray-500">{tt.upcoming_12m[0].symbol} — {remainLabel(tt.upcoming_12m[0].days_remaining)}</div>
            </>
          ) : <div className="mt-1 text-sm text-gray-500">žádné v nejbližších 12 měsících</div>}
        </div>
      </div>

      {s && !s.complete && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/[0.05] px-4 py-2 text-[12px] text-amber-300/80">
          <AlertCircle size={14} /> Některé částky nejdou přepočítat do CZK (chybí živá cena/FX) — hodnoty jsou neúplné.
        </div>
      )}

      {/* Blíží se */}
      {tt?.upcoming_12m.length ? (
        <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-5">
          <h2 className="text-sm font-semibold text-white">Blíží se osvobození (do 12 měsíců)</h2>
          <ul className="mt-3 space-y-1.5">
            {tt.upcoming_12m.map((l, i) => (
              <li key={i} className="text-[13px] text-gray-300">
                <span className="font-medium text-white">{l.symbol}</span> — {fmt(l.quantity)} ks z {dCZ(l.buy_date)} →
                <span className="text-amber-300"> osvobozeno {dCZ(l.free_date)}</span> ({remainLabel(l.days_remaining)})
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-gray-500">Počkáš-li s prodejem na datum osvobození, zisk z těchto nákupů je bez daně z příjmu.</p>
        </div>
      ) : null}

      {/* Všechny loty */}
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
        <div className="border-b border-[#2a2d3a] px-4 py-3 text-sm font-semibold text-white">Nákupní pozice ({tt?.lots.length ?? 0})</div>
        {loading ? (
          <div className="p-6 text-sm text-gray-500">Načítám…</div>
        ) : !tt?.lots.length ? (
          <div className="p-6 text-sm text-gray-500">Žádné otevřené nákupy. Nahraj transakce v <a href="/investice" className="text-[#60ff82] underline">Investicích</a>.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase text-gray-500">
                  <th className="px-4 py-2 font-medium">Ticker</th>
                  <th className="px-4 py-2 font-medium text-right">Počet</th>
                  <th className="px-4 py-2 font-medium">Datum nákupu</th>
                  <th className="px-4 py-2 font-medium text-right">Hodnota</th>
                  <th className="px-4 py-2 font-medium">Osvobozeno od</th>
                  <th className="px-4 py-2 font-medium">Stav</th>
                </tr>
              </thead>
              <tbody>
                {tt.lots.map((l, i) => (
                  <tr key={i} className="border-t border-[#20242f]">
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-white">{l.symbol}</div>
                      {l.name && <div className="text-[11px] text-gray-500 truncate max-w-[160px]">{l.name}</div>}
                    </td>
                    <td className="px-4 py-2.5 text-right text-gray-300">{l.quantity.toLocaleString("cs-CZ", { maximumFractionDigits: 4 })}</td>
                    <td className="px-4 py-2.5 text-gray-400">{dCZ(l.buy_date)}</td>
                    <td className="px-4 py-2.5 text-right text-gray-300">{l.value === null ? fmt(l.cost, l.currency) : fmt(l.value, l.currency)}</td>
                    <td className="px-4 py-2.5 text-gray-400">{dCZ(l.free_date)}</td>
                    <td className="px-4 py-2.5">
                      {l.tax_free ? (
                        <span className="inline-flex items-center gap-1 rounded bg-[rgba(96,255,130,0.14)] px-2 py-0.5 text-[11px] text-[#8fffab]"><CheckCircle2 size={11} /> osvobozeno</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded bg-[#2a2d3a] px-2 py-0.5 text-[11px] text-gray-300"><Clock size={11} /> {remainLabel(l.days_remaining)}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Vysvětlení + disclaimer */}
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-5 text-[13px] text-gray-300 space-y-2">
        <h2 className="text-sm font-semibold text-white">Jak to funguje</h2>
        <p><strong className="text-white">Časový test 3 roky:</strong> když cenný papír (akcie, ETF) držíš déle než 3 roky, příjem z jeho prodeje je osvobozen od daně z příjmu fyzických osob. Datum osvobození = datum nákupu + 3 roky. U částečných prodejů se dřívější nákupy prodávají první (FIFO).</p>
        <p><strong className="text-white">Limit 100 000 Kč:</strong> pokud je souhrn <em>příjmů</em> (ne zisku) z prodeje cenných papírů za rok do 100 000 Kč, je osvobozen i bez splnění časového testu.</p>
        <p className="text-[11px] text-gray-500">Orientační výpočet podle obecných pravidel, <strong>není to daňové poradenství</strong>. Pravidla se mění (např. od 2025 strop osvobození 40 mil. Kč příjmů/rok) a tvoje situace může mít výjimky — ověř si to s daňovým poradcem.</p>
      </div>
    </div>
  );
}
