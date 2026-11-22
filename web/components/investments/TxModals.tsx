"use client";

// Sdílené dialogy investorského deníku: nová transakce, import (XTB xlsx / CSV), obecný modal.
// Používá je stránka Investice (pokročilý režim) i Moje portfolio (jednoduchý režim).
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { authHeaders } from "@/lib/auth";

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex flex-col gap-1.5"><span className="text-xs text-gray-400">{label}</span>{children}</label>;
}

export interface TxDraft { tx_type?: string; symbol?: string; name?: string; currency?: string; price?: string; quantity?: string; broker?: string }

/** Nová transakce. `initial` předvyplní pole (jednoduchý režim: „Zapsat nákup“ z plánu). */
export function AddTxModal({ onClose, onSaved, initial, title = "Nová transakce" }: { onClose: () => void; onSaved: () => void; initial?: TxDraft; title?: string }) {
  const [f, setF] = useState({ tx_type: "buy", symbol: "", name: "", quantity: "", price: "", currency: "USD", fee: "", amount: "", executed_at: new Date().toISOString().slice(0, 10), broker: "manual", ...initial });
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
    <Modal title={title} onClose={onClose}>
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
          <button type="button" onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-gray-300">Zrušit</button>
          <button type="submit" disabled={busy} className="flex items-center gap-1.5 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-4 py-2 text-sm font-medium text-neon-soft disabled:opacity-50">
            {busy && <Loader2 size={14} className="animate-spin" />} Uložit
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ── Import: XTB výpis (xlsx, parser na backendu s kontrolou proti otevřeným pozicím) nebo obecné CSV ──
interface XtbSummary {
  account: string | null; currency: string; total: number; new: number; already: number;
  by_type: Record<string, number>; skipped: Record<string, number>; legacy: number;
  check: { symbol: string; z_transakci: number; xtb_otevreno: number }[]; open_positions: number;
  created?: number; replaced_legacy?: number;
}
const TYPE_CS: Record<string, string> = { buy: "nákupy", sell: "prodeje", dividend: "dividendy a daně z nich", deposit: "vklady", withdrawal: "výběry", interest: "úroky", tax: "daně z úroků" };

export function ImportModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [broker, setBroker] = useState("xtb");
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [b64, setB64] = useState<string | null>(null);
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [preview, setPreview] = useState<XtbSummary | null>(null);
  const [replaceLegacy, setReplaceLegacy] = useState(true);
  const xtb = broker === "xtb";

  const xtbCall = async (data: string, dry: boolean) => {
    const res = await fetch("/api/investments/import/xtb", {
      method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ content_b64: data, dry_run: dry, replace_legacy: replaceLegacy, source: fileName }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(d.detail || "Import selhal");
    return d as XtbSummary;
  };

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name); setResult(null); setPreview(null); setRows([]); setB64(null);
    if (xtb) {
      const buf = new Uint8Array(await file.arrayBuffer());
      let bin = "";
      for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
      const data = btoa(bin);
      setB64(data); setBusy(true);
      try { setPreview(await xtbCall(data, true)); }
      catch (err) { setResult((err as Error).message); }
      finally { setBusy(false); }
    } else {
      setRows(parseCSV(await file.text()));
    }
  };

  const doImport = async () => {
    setBusy(true); setResult(null);
    try {
      if (xtb && b64) {
        const d = await xtbCall(b64, false);
        setResult(`Přidáno ${d.created} transakcí${d.replaced_legacy ? `, nahrazeno ${d.replaced_legacy} ze staršího importu` : ""}.`);
        setTimeout(onDone, 1200);
      } else {
        const mapped = rows.map((r) => mapRow(r, broker));
        const res = await fetch("/api/investments/import", { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ rows: mapped, broker, source: fileName }) });
        const d = await res.json();
        setResult(`Přidáno ${d.created}, přeskočeno ${d.skipped}${d.errors?.length ? `, chyby: ${d.errors.length}` : ""}`);
        if (d.created > 0) setTimeout(onDone, 1200);
      }
    } catch (err) { setResult((err as Error).message || "Import selhal."); } finally { setBusy(false); }
  };

  const ready = xtb ? !!preview && preview.new + (replaceLegacy ? preview.legacy : 0) > 0 : rows.length > 0;
  return (
    <Modal title="Import transakcí" onClose={onClose}>
      <div className="space-y-4">
        <Field label="Broker">
          <select className="inv-input" value={broker} onChange={(e) => { setBroker(e.target.value); setPreview(null); setRows([]); setB64(null); setResult(null); }}>
            <option value="xtb">XTB (výpis .xlsx)</option><option value="etoro">eToro (CSV)</option>
            <option value="trading212">Trading212 (CSV)</option><option value="portu">Portu (CSV)</option>
            <option value="manual">Obecné CSV</option>
          </select>
        </Field>
        <Field label={xtb ? "Výpis z XTB (.xlsx)" : "Soubor CSV"}>
          <input type="file" accept={xtb ? ".xlsx" : ".csv,text/csv"} onChange={onFile} className="text-sm text-gray-300 file:mr-3 file:rounded file:border-0 file:bg-raised file:px-3 file:py-1.5 file:text-gray-200" />
        </Field>
        {xtb && !preview && !busy && (
          <p className="text-[11px] text-gray-500">V XTB: Historie účtu → zvolit celé období → Export do Excelu. Nahrát můžeš opakovaně, už importované operace se přeskočí.</p>
        )}
        {busy && !preview && <p className="flex items-center gap-2 text-sm text-gray-400"><Loader2 size={14} className="animate-spin" /> Čtu výpis…</p>}
        {preview && (
          <div className="space-y-2 rounded-lg border border-line bg-panel p-3 text-[13px] text-gray-300">
            <div>
              Účet {preview.account} ({preview.currency}): <b className="text-white">{preview.new} nových</b> transakcí
              {preview.already > 0 && <span className="text-gray-500"> · {preview.already} už v Tradezeru je</span>}
            </div>
            {Object.keys(preview.by_type).length > 0 && (
              <div className="text-gray-400">{Object.entries(preview.by_type).map(([k, v]) => `${v} ${TYPE_CS[k] ?? k}`).join(" · ")}</div>
            )}
            {Object.keys(preview.skipped).length > 0 && (
              <div className="text-[12px] text-gray-500">Přeskočeno: {Object.entries(preview.skipped).map(([k, v]) => `${v}× ${k}`).join(", ")} (CFD patří do Deníku).</div>
            )}
            {preview.check.length === 0
              ? <div className="text-[12px] text-neon-soft">✓ Počty kusů sedí se všemi {preview.open_positions} otevřenými pozicemi v XTB.</div>
              : <div className="text-[12px] text-amber-300">Pozor, nesedí: {preview.check.map((c) => `${c.symbol} (${c.z_transakci} vs. XTB ${c.xtb_otevreno})`).join(", ")}</div>}
            {preview.legacy > 0 && (
              <label className="flex items-start gap-2 text-[12px] text-gray-300">
                <input type="checkbox" className="mt-0.5" checked={replaceLegacy} onChange={(e) => setReplaceLegacy(e.target.checked)} />
                Nahradit {preview.legacy} XTB transakcí ze staršího importu (jinak se pozice zdvojí)
              </label>
            )}
          </div>
        )}
        {!xtb && rows.length > 0 && <p className="text-sm text-gray-400">Načteno {rows.length} řádků{fileName ? ` ze souboru ${fileName}` : ""}. Sloupce se namapují automaticky podle hlaviček.</p>}
        {result && <p className="text-sm text-neon-soft">{result}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-gray-300">Zavřít</button>
          <button onClick={doImport} disabled={busy || !ready} className="flex items-center gap-1.5 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-4 py-2 text-sm font-medium text-neon-soft disabled:opacity-50">
            {busy && preview && <Loader2 size={14} className="animate-spin" />} Importovat
          </button>
        </div>
      </div>
    </Modal>
  );
}

export function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-line bg-dialog shadow-2xl p-5 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
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
