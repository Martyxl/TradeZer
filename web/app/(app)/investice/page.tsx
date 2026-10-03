"use client";

import { useEffect, useMemo, useState } from "react";
import { Wallet, Plus, Upload, Trash2, Loader2, TrendingUp, Calculator, RefreshCw } from "lucide-react";
import { useAuth, authHeaders } from "@/lib/auth";

// ── Typy ────────────────────────────────────────────────────────────────────
interface Signal {
  color: "green" | "amber" | "red"; reasons: string[]; action: string;
  trim_qty: number | null; add_zone: number | null; pos_52w: number | null;
}
interface Holding {
  symbol: string; name: string | null; quantity: number; avg_cost: number;
  invested: number; currency: string; price: number | null; value: number | null;
  unrealized: number | null; unrealized_pct: number | null; price_as_of: string | null;
  weight_pct: number | null; high_52w: number | null; low_52w: number | null; signal: Signal;
}
interface Portfolio {
  base: string; holdings: Holding[];
  by_currency: Record<string, { invested: number; value: number | null }>;
  realized_by_currency: Record<string, number>;
  dividends_by_currency: Record<string, number>;
  base_totals: { invested: number; value: number; unrealized: number; complete: boolean };
  fx_available: string[];
}
interface Tx {
  id: number; broker: string; tx_type: string; symbol: string | null; name: string | null;
  quantity: number | null; price: number | null; currency: string; fee: number | null;
  amount: number | null; executed_at: string | null; notes: string | null;
}

const fmt = (n: number | null | undefined, ccy = "") =>
  n === null || n === undefined ? "—" : `${n.toLocaleString("cs-CZ", { maximumFractionDigits: 2 })}${ccy ? " " + ccy : ""}`;
const pct = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(2)} %`);
const pnlColor = (n: number | null | undefined) =>
  n === null || n === undefined ? "text-gray-400" : n > 0 ? "text-[#60ff82]" : n < 0 ? "text-[#ff5050]" : "text-gray-300";

export default function InvesticePage() {
  const { user, loading: authLoading } = useAuth();
  const [pf, setPf] = useState<Portfolio | null>(null);
  const [txs, setTxs] = useState<Tx[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [showImport, setShowImport] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [p, t] = await Promise.all([
        fetch("/api/investments/portfolio?base=CZK", { headers: authHeaders() }).then((r) => (r.ok ? r.json() : null)),
        fetch("/api/investments", { headers: authHeaders() }).then((r) => (r.ok ? r.json() : null)),
      ]);
      setPf(p);
      setTxs(t?.transactions ?? []);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { if (user) load(); /* eslint-disable-next-line */ }, [user]);

  if (authLoading) return <div className="h-40 animate-pulse rounded-xl bg-[#1a1d27]" />;
  if (!user)
    return (
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-8 text-center text-gray-400">
        Pro investorský deník se <a href="/prihlaseni" className="text-[#60ff82] underline">přihlas</a>.
      </div>
    );

  const bt = pf?.base_totals;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <Wallet size={20} className="text-[#60ff82]" /> Investiční portfolio
          </h1>
          <p className="mt-1 text-sm text-gray-400">Nákupy, prodeje a dividendy — s živou hodnotou a výhledem.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="flex items-center gap-1.5 rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-3 py-2 text-sm text-gray-200 hover:border-gray-500">
            <RefreshCw size={14} /> Obnovit
          </button>
          <button onClick={() => setShowImport(true)} className="flex items-center gap-1.5 rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-3 py-2 text-sm text-gray-200 hover:border-gray-500">
            <Upload size={14} /> Import CSV
          </button>
          <button onClick={() => setShowAdd(true)} className="flex items-center gap-1.5 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-3 py-2 text-sm font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)]">
            <Plus size={14} /> Přidat transakci
          </button>
        </div>
      </div>

      {/* Souhrnné karty (base CZK) */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard label="Investováno" value={fmt(bt?.invested, "CZK")} />
        <SummaryCard label="Aktuální hodnota" value={fmt(bt?.value, "CZK")} hint={bt && !bt.complete ? "neúplné — chybí ceny/FX" : undefined} />
        <SummaryCard label="Nerealizovaný P/L" value={fmt(bt?.unrealized, "CZK")} color={pnlColor(bt?.unrealized)}
          sub={bt && bt.invested ? pct((bt.unrealized / bt.invested) * 100) : undefined} />
        <SummaryCard label="Realizováno + dividendy" value={realizedSummary(pf)} color="text-gray-200" />
      </div>

      {/* Holdings */}
      <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
        <div className="border-b border-[#2a2d3a] px-4 py-3 text-sm font-semibold text-white">Pozice</div>
        {loading ? (
          <div className="p-6 text-sm text-gray-500">Načítám…</div>
        ) : !pf?.holdings.length ? (
          <div className="p-6 text-sm text-gray-500">Zatím žádné otevřené pozice. Přidej transakci nebo importuj CSV.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase text-gray-500">
                  <th className="px-4 py-2 font-medium">Ticker</th>
                  <th className="px-4 py-2 font-medium text-right">Počet</th>
                  <th className="px-4 py-2 font-medium text-right">Prům. cena</th>
                  <th className="px-4 py-2 font-medium text-right">Investováno</th>
                  <th className="px-4 py-2 font-medium text-right">Cena</th>
                  <th className="px-4 py-2 font-medium text-right">Hodnota</th>
                  <th className="px-4 py-2 font-medium text-right">P/L</th>
                  <th className="px-4 py-2 font-medium">Semafor</th>
                </tr>
              </thead>
              <tbody>
                {pf.holdings.map((h) => (
                  <tr key={h.symbol} className="border-t border-[#20242f]">
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-white">{h.symbol}</div>
                      {h.name && <div className="text-[11px] text-gray-500 truncate max-w-[180px]">{h.name}</div>}
                    </td>
                    <td className="px-4 py-2.5 text-right text-gray-300">{fmt(h.quantity)}</td>
                    <td className="px-4 py-2.5 text-right text-gray-300">{fmt(h.avg_cost, h.currency)}</td>
                    <td className="px-4 py-2.5 text-right text-gray-300">{fmt(h.invested, h.currency)}</td>
                    <td className="px-4 py-2.5 text-right text-gray-300">{h.price === null ? "—" : fmt(h.price, h.currency)}</td>
                    <td className="px-4 py-2.5 text-right text-gray-200">{fmt(h.value, h.currency)}{h.weight_pct !== null && <div className="text-[10px] text-gray-500">{h.weight_pct}% portfolia</div>}</td>
                    <td className={`px-4 py-2.5 text-right ${pnlColor(h.unrealized)}`}>
                      {h.unrealized === null ? "—" : <>{fmt(h.unrealized, h.currency)}<div className="text-[11px]">{pct(h.unrealized_pct)}</div></>}
                    </td>
                    <td className="px-4 py-2.5"><SignalCell h={h} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pf && !pf.base_totals.complete && (
          <div className="border-t border-[#2a2d3a] px-4 py-2 text-[11px] text-amber-400/80">
            Živé ceny se plní z externího skenu (Yahoo). Dokud nedorazí ceny/FX, hodnota je neúplná.
          </div>
        )}
      </div>

      {/* Semafor — co zvážit */}
      {pf?.holdings.length ? <SignalSummary holdings={pf.holdings} /> : null}

      {/* Kalkulačka výhledu */}
      <ProjectionCalculator startValue={bt?.value ?? 0} />

      {/* Transakce */}
      <TxTable txs={txs} onDeleted={load} />

      {showAdd && <AddTxModal onClose={() => setShowAdd(false)} onSaved={() => { setShowAdd(false); load(); }} />}
      {showImport && <ImportModal onClose={() => setShowImport(false)} onDone={() => { setShowImport(false); load(); }} />}

      <style>{`.inv-input{min-height:36px;padding:6px 10px;font-size:14px;color:#e5e7eb;background:#0f1117;border:1px solid #2a2d3a;border-radius:8px;outline:none;width:100%}.inv-input:focus{border-color:#60ff82}`}</style>
    </div>
  );
}

function realizedSummary(pf: Portfolio | null): string {
  if (!pf) return "—";
  const parts: string[] = [];
  for (const [c, v] of Object.entries(pf.realized_by_currency)) if (v) parts.push(`${fmt(v)} ${c}`);
  const div = Object.entries(pf.dividends_by_currency).reduce((a, [, v]) => a + (v || 0), 0);
  if (!parts.length && !div) return "0";
  return parts.join(" · ") || "0";
}

const DOT: Record<string, string> = { red: "bg-[#ff5050]", amber: "bg-amber-400", green: "bg-[#60ff82]" };
const SIG_LABEL: Record<string, string> = { red: "Zvážit odebrání", amber: "Držet", green: "Prostor dokupovat" };

function SignalCell({ h }: { h: Holding }) {
  const s = h.signal;
  const tip = [
    s.reasons.length ? "Důvody: " + s.reasons.join(", ") : "",
    s.pos_52w !== null ? `Poloha v 52T rozpětí: ${s.pos_52w} %` : "",
    s.add_zone !== null ? `Zóna k dokupu: ~${fmt(s.add_zone, h.currency)}` : "",
  ].filter(Boolean).join("\n");
  return (
    <div className="flex items-start gap-2" title={tip}>
      <span className={`mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-full ${DOT[s.color]}`} />
      <div className="min-w-0">
        <div className="text-[12px] text-gray-200">{s.action}</div>
        {s.add_zone !== null && <div className="text-[10px] text-gray-500">dokup ~{fmt(s.add_zone, h.currency)}</div>}
      </div>
    </div>
  );
}

function SignalSummary({ holdings }: { holdings: Holding[] }) {
  const reds = holdings.filter((h) => h.signal.color === "red");
  const greens = holdings.filter((h) => h.signal.color === "green");
  if (!reds.length && !greens.length) return null;
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-5">
      <h2 className="text-sm font-semibold text-white">Co zvážit (semafor)</h2>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {reds.length > 0 && (
          <div>
            <div className="mb-1.5 flex items-center gap-2 text-[11px] uppercase text-[#ff8080]"><span className="h-2 w-2 rounded-full bg-[#ff5050]" /> Zvážit odebrání</div>
            <ul className="space-y-1.5">
              {reds.map((h) => (
                <li key={h.symbol} className="text-[13px] text-gray-300">
                  <span className="font-medium text-white">{h.symbol}</span> — {h.signal.action}
                  {h.signal.reasons.length > 0 && <span className="text-gray-500"> ({h.signal.reasons.join(", ")})</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {greens.length > 0 && (
          <div>
            <div className="mb-1.5 flex items-center gap-2 text-[11px] uppercase text-[#8fffab]"><span className="h-2 w-2 rounded-full bg-[#60ff82]" /> Prostor dokupovat</div>
            <ul className="space-y-1.5">
              {greens.map((h) => (
                <li key={h.symbol} className="text-[13px] text-gray-300">
                  <span className="font-medium text-white">{h.symbol}</span>
                  {h.signal.add_zone !== null && <span className="text-gray-500"> — zóna ~{fmt(h.signal.add_zone, h.currency)}</span>}
                  {h.signal.reasons.length > 0 && <span className="text-gray-500"> ({h.signal.reasons.join(", ")})</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <p className="mt-3 text-[11px] text-gray-500">
        Semafor je orientační pravidlový signál (zisk, váha v portfoliu, poloha v 52týdenním rozpětí), <strong>ne investiční doporučení</strong>. Rozhoduješ sám.
      </p>
    </div>
  );
}

function SummaryCard({ label, value, sub, hint, color = "text-white" }: { label: string; value: string; sub?: string; hint?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <div className="text-[11px] uppercase text-gray-500">{label}</div>
      <div className={`mt-1 text-xl font-bold ${color}`}>{value}</div>
      {sub && <div className={`text-xs ${color}`}>{sub}</div>}
      {hint && <div className="text-[10px] text-amber-400/70">{hint}</div>}
    </div>
  );
}

// ── Kalkulačka 5/10letého výhledu (složené úročení) ─────────────────────────
function ProjectionCalculator({ startValue }: { startValue: number }) {
  const [start, setStart] = useState(Math.round(startValue) || 100000);
  const [monthly, setMonthly] = useState(5000);
  const [rate, setRate] = useState(7);
  const [years, setYears] = useState(5);

  useEffect(() => { if (startValue) setStart(Math.round(startValue)); }, [startValue]);

  const series = useMemo(() => {
    const r = rate / 100 / 12;
    const pts: { year: number; value: number; contributed: number }[] = [];
    let val = start;
    let contributed = start;
    for (let m = 1; m <= years * 12; m++) {
      val = val * (1 + r) + monthly;
      contributed += monthly;
      if (m % 12 === 0) pts.push({ year: m / 12, value: val, contributed });
    }
    return pts;
  }, [start, monthly, rate, years]);

  const final = series.length ? series[series.length - 1] : { value: start, contributed: start };
  const gain = final.value - final.contributed;
  const maxV = Math.max(...series.map((p) => p.value), start, 1);

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
        <Calculator size={15} className="text-[#60ff82]" /> Výhled portfolia (složené úročení)
      </h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        <Field label="Počáteční (CZK)"><input type="number" className="inv-input" value={start} onChange={(e) => setStart(+e.target.value)} /></Field>
        <Field label="Měsíčně (CZK)"><input type="number" className="inv-input" value={monthly} onChange={(e) => setMonthly(+e.target.value)} /></Field>
        <Field label="Výnos ročně (%)"><input type="number" step="0.5" className="inv-input" value={rate} onChange={(e) => setRate(+e.target.value)} /></Field>
        <Field label="Roky"><input type="number" className="inv-input" value={years} onChange={(e) => setYears(Math.max(1, Math.min(40, +e.target.value)))} /></Field>
      </div>

      {/* Sloupcový graf */}
      <div className="mt-5 flex items-end gap-2 h-40">
        {series.map((p) => (
          <div key={p.year} className="flex flex-1 flex-col items-center justify-end gap-1" title={`Rok ${p.year}: ${fmt(Math.round(p.value))} CZK`}>
            <div className="w-full rounded-t bg-gradient-to-t from-[#1e6b3a] to-[#60ff82]" style={{ height: `${(p.value / maxV) * 100}%` }} />
            <div className="text-[10px] text-gray-500">{p.year}r</div>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3 text-sm">
        <div><div className="text-[11px] uppercase text-gray-500">Za {years} let</div><div className="text-lg font-bold text-white">{fmt(Math.round(final.value))} CZK</div></div>
        <div><div className="text-[11px] uppercase text-gray-500">Vloženo celkem</div><div className="text-lg font-bold text-gray-300">{fmt(Math.round(final.contributed))} CZK</div></div>
        <div><div className="text-[11px] uppercase text-gray-500">Výnos (úroky)</div><div className="text-lg font-bold text-[#60ff82]">+{fmt(Math.round(gain))} CZK</div></div>
      </div>
      <p className="mt-3 text-[11px] text-gray-500">Zjednodušený model (konstantní výnos, měsíční vklad na konci měsíce). Není investiční doporučení.</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex flex-col gap-1.5"><span className="text-xs text-gray-400">{label}</span>{children}</label>;
}

// ── Transakce ───────────────────────────────────────────────────────────────
function TxTable({ txs, onDeleted }: { txs: Tx[]; onDeleted: () => void }) {
  const [busy, setBusy] = useState<number | null>(null);
  const del = async (id: number) => {
    if (!confirm("Smazat transakci?")) return;
    setBusy(id);
    try {
      await fetch(`/api/investments/${id}`, { method: "DELETE", headers: authHeaders() });
      onDeleted();
    } finally { setBusy(null); }
  };
  const TYPE_LABEL: Record<string, string> = { buy: "Nákup", sell: "Prodej", dividend: "Dividenda", fee: "Poplatek", deposit: "Vklad", withdrawal: "Výběr" };

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
      <div className="border-b border-[#2a2d3a] px-4 py-3 text-sm font-semibold text-white">Transakce ({txs.length})</div>
      {!txs.length ? (
        <div className="p-6 text-sm text-gray-500">Žádné transakce.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase text-gray-500">
                <th className="px-4 py-2 font-medium">Datum</th>
                <th className="px-4 py-2 font-medium">Typ</th>
                <th className="px-4 py-2 font-medium">Ticker</th>
                <th className="px-4 py-2 font-medium text-right">Počet</th>
                <th className="px-4 py-2 font-medium text-right">Cena</th>
                <th className="px-4 py-2 font-medium">Broker</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {txs.map((t) => (
                <tr key={t.id} className="border-t border-[#20242f]">
                  <td className="px-4 py-2.5 text-gray-400">{t.executed_at ? t.executed_at.slice(0, 10) : "—"}</td>
                  <td className="px-4 py-2.5 text-gray-300">{TYPE_LABEL[t.tx_type] ?? t.tx_type}</td>
                  <td className="px-4 py-2.5 text-white">{t.symbol ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right text-gray-300">{fmt(t.quantity)}</td>
                  <td className="px-4 py-2.5 text-right text-gray-300">{t.price === null ? fmt(t.amount, t.currency) : fmt(t.price, t.currency)}</td>
                  <td className="px-4 py-2.5 text-gray-500 uppercase text-[11px]">{t.broker}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => del(t.id)} disabled={busy === t.id} className="text-gray-500 hover:text-red-400">
                      {busy === t.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AddTxModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ tx_type: "buy", symbol: "", name: "", quantity: "", price: "", currency: "USD", fee: "", amount: "", executed_at: new Date().toISOString().slice(0, 10), broker: "manual" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      const res = await fetch("/api/investments", { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(f) });
      if (res.ok) onSaved();
      else { const d = await res.json().catch(() => ({})); setErr(d.detail || "Uložení selhalo"); }
    } catch { setErr("Chyba připojení"); } finally { setBusy(false); }
  };

  const needsSymbol = f.tx_type === "buy" || f.tx_type === "sell";
  return (
    <Modal title="Nová transakce" onClose={onClose}>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <Field label="Typ">
          <select className="inv-input" value={f.tx_type} onChange={(e) => set("tx_type", e.target.value)}>
            <option value="buy">Nákup</option><option value="sell">Prodej</option>
            <option value="dividend">Dividenda</option><option value="fee">Poplatek</option>
            <option value="deposit">Vklad</option><option value="withdrawal">Výběr</option>
          </select>
        </Field>
        <Field label="Datum"><input type="date" className="inv-input" value={f.executed_at} onChange={(e) => set("executed_at", e.target.value)} /></Field>
        <Field label={`Ticker ${needsSymbol ? "*" : "(volitelné)"}`}><input className="inv-input" value={f.symbol} onChange={(e) => set("symbol", e.target.value)} placeholder="AAPL" required={needsSymbol} /></Field>
        <Field label="Název (volitelné)"><input className="inv-input" value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="Apple Inc." /></Field>
        <Field label="Počet kusů"><input type="number" step="any" className="inv-input" value={f.quantity} onChange={(e) => set("quantity", e.target.value)} /></Field>
        <Field label="Cena za kus"><input type="number" step="any" className="inv-input" value={f.price} onChange={(e) => set("price", e.target.value)} /></Field>
        <Field label="Měna">
          <select className="inv-input" value={f.currency} onChange={(e) => set("currency", e.target.value)}>
            {["USD", "EUR", "CZK", "GBP"].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Poplatek (volitelné)"><input type="number" step="any" className="inv-input" value={f.fee} onChange={(e) => set("fee", e.target.value)} /></Field>
        {!needsSymbol && <Field label="Částka (dividenda/vklad)"><input type="number" step="any" className="inv-input" value={f.amount} onChange={(e) => set("amount", e.target.value)} /></Field>}
        {err && <p className="sm:col-span-2 text-sm text-red-400">{err}</p>}
        <div className="sm:col-span-2 mt-1 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-[#2a2d3a] px-4 py-2 text-sm text-gray-300">Zrušit</button>
          <button type="submit" disabled={busy} className="flex items-center gap-1.5 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-4 py-2 text-sm font-medium text-[#8fffab] disabled:opacity-50">
            {busy && <Loader2 size={14} className="animate-spin" />} Uložit
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ── CSV import (generické mapování; broker-specifické parsery doplníme ze vzorků) ──
function ImportModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [broker, setBroker] = useState("manual");
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const text = await file.text();
    setRows(parseCSV(text));
  };

  const doImport = async () => {
    setBusy(true); setResult(null);
    try {
      const mapped = rows.map((r) => mapRow(r, broker));
      const res = await fetch("/api/investments/import", { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ rows: mapped, broker, source: fileName }) });
      const d = await res.json();
      setResult(`Přidáno ${d.created}, přeskočeno ${d.skipped}${d.errors?.length ? `, chyby: ${d.errors.length}` : ""}`);
      if (d.created > 0) setTimeout(onDone, 1200);
    } catch { setResult("Import selhal."); } finally { setBusy(false); }
  };

  return (
    <Modal title="Import transakcí z CSV" onClose={onClose}>
      <div className="space-y-4">
        <Field label="Broker">
          <select className="inv-input" value={broker} onChange={(e) => setBroker(e.target.value)}>
            <option value="xtb">XTB</option><option value="etoro">eToro</option>
            <option value="trading212">Trading212</option><option value="portu">Portu</option>
            <option value="manual">Obecné CSV</option>
          </select>
        </Field>
        <Field label="Soubor CSV"><input type="file" accept=".csv,text/csv" onChange={onFile} className="text-sm text-gray-300 file:mr-3 file:rounded file:border-0 file:bg-[#1e2536] file:px-3 file:py-1.5 file:text-gray-200" /></Field>
        {rows.length > 0 && <p className="text-sm text-gray-400">Načteno {rows.length} řádků{fileName ? ` ze souboru ${fileName}` : ""}. Sloupce se namapují automaticky podle hlaviček (ticker, typ, počet, cena, měna, datum, poplatek).</p>}
        {result && <p className="text-sm text-[#8fffab]">{result}</p>}
        <p className="text-[11px] text-gray-500">Přesné parsery pro XTB a eToro dolaďujeme podle reálných exportů. Zatím funguje obecné mapování sloupců — po dodání vzorků bude detekce 1:1.</p>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-[#2a2d3a] px-4 py-2 text-sm text-gray-300">Zavřít</button>
          <button onClick={doImport} disabled={busy || !rows.length} className="flex items-center gap-1.5 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-4 py-2 text-sm font-medium text-[#8fffab] disabled:opacity-50">
            {busy && <Loader2 size={14} className="animate-spin" />} Importovat
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-[#2a2d3a] bg-[#12141c] p-5 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-lg font-semibold text-white">{title}</h2>
        {children}
      </div>
    </div>
  );
}

// ── CSV helpers ──────────────────────────────────────────────────────────────
function parseCSV(text: string): Record<string, string>[] {
  const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim());
  if (lines.length < 2) return [];
  const delim = (lines[0].match(/;/g)?.length ?? 0) > (lines[0].match(/,/g)?.length ?? 0) ? ";" : ",";
  const split = (l: string) => {
    const out: string[] = []; let cur = ""; let q = false;
    for (const ch of l) {
      if (ch === '"') q = !q;
      else if (ch === delim && !q) { out.push(cur); cur = ""; }
      else cur += ch;
    }
    out.push(cur);
    return out.map((s) => s.trim().replace(/^"|"$/g, ""));
  };
  const headers = split(lines[0]);
  return lines.slice(1).map((l) => {
    const cells = split(l);
    const row: Record<string, string> = {};
    headers.forEach((h, i) => (row[h] = cells[i] ?? ""));
    return row;
  });
}

function pick(row: Record<string, string>, keys: string[]): string {
  for (const k of Object.keys(row)) if (keys.some((n) => k.toLowerCase().includes(n))) return row[k];
  return "";
}

function mapRow(row: Record<string, string>, broker: string): Record<string, string> {
  const actionRaw = pick(row, ["action", "typ", "type", "direction"]).toLowerCase();
  let tx_type = "buy";
  if (/sell|prodej|sold/.test(actionRaw)) tx_type = "sell";
  else if (/div/.test(actionRaw)) tx_type = "dividend";
  else if (/depos|vklad/.test(actionRaw)) tx_type = "deposit";
  else if (/withdr|výběr|vyber/.test(actionRaw)) tx_type = "withdrawal";
  else if (/fee|poplat/.test(actionRaw)) tx_type = "fee";
  return {
    broker,
    tx_type,
    symbol: pick(row, ["ticker", "symbol", "isin", "instrument"]),
    name: pick(row, ["name", "název", "nazev"]),
    quantity: pick(row, ["shares", "quantity", "počet", "pocet", "units", "množství", "mnozstvi"]),
    price: pick(row, ["price", "cena", "rate", "open rate"]),
    currency: pick(row, ["currency", "měna", "mena"]) || "USD",
    fee: pick(row, ["fee", "poplatek", "commission"]),
    amount: pick(row, ["amount", "total", "částka", "castka", "value"]),
    executed_at: pick(row, ["time", "date", "datum", "executed"]),
  };
}
