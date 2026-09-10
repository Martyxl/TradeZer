"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { NotebookPen, Plus, Pencil, Trash2, X, ExternalLink, TrendingUp, Sparkles, Upload } from "lucide-react";
import { authToken, useAuth } from "@/lib/auth";
import Link from "next/link";

/* ---------------------------------------------------------------- typy */

interface Entry {
  id: number;
  instrument: string;
  direction: "long" | "short";
  entry_price: number | null;
  exit_price: number | null;
  size: number | null;
  r_result: number | null;
  pnl: number | null;
  traded_at: string | null;
  session: string | null;
  setup: string | null;
  notes: string | null;
  screenshot_url: string | null;
  created_at: string | null;
}
interface Bucket { key: string; n: number; win_rate: number | null; avg_r: number | null }
interface Stats {
  totals: {
    trades: number; decided: number; wins: number; losses: number; breakeven: number;
    win_rate: number | null; avg_r: number | null; sum_r: number | null;
    best_r: number | null; worst_r: number | null; sum_pnl: number | null;
  };
  by_setup: Bucket[];
  by_session: Bucket[];
  by_instrument: Bucket[];
}
interface AnalysisMeta {
  engine?: string; model?: string; ms?: number;
  in_tokens?: number | null; out_tokens?: number | null; total_tokens?: number | null;
}

/* ------------------------------------------------------------ pomocné */

async function jFetch(path: string, opts: { method?: string; body?: unknown } = {}) {
  const token = authToken();
  const res = await fetch(`/api/journal${path}`, {
    method: opts.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string })?.detail || "Něco se pokazilo");
  return data;
}

const SESSION_OPTS: [string, string][] = [
  ["", "—"], ["asia", "Asia"], ["london", "London"], ["ny", "NY"], ["other", "Jiné"],
];
const SESSION_NAME: Record<string, string> = { asia: "Asia", london: "London", ny: "NY", other: "Jiné" };

function rColor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "#9ca3af";
  return v > 0 ? "#4ade80" : v < 0 ? "#f87171" : "#9ca3af";
}
function outcomeOf(e: Entry): number | null {
  return e.r_result ?? e.pnl ?? null;
}
function fmtDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s.slice(0, 16).replace("T", " ");
  return d.toLocaleString("cs", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
}
function toLocalInput(s: string | null): string {
  if (!s) return "";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function nowLocalInput(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/* -------------------------------------------------------------- stat karta */

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-2xl font-bold mt-1" style={{ color: color || "#fff" }}>{value}</div>
      {sub && <div className="text-[11px] text-gray-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function BucketTable({ title, rows, nameMap }: { title: string; rows: Bucket[]; nameMap?: Record<string, string> }) {
  if (!rows.length) return null;
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 text-[10px] uppercase">
            <th className="text-left pb-2">Kategorie</th>
            <th className="text-right pb-2">Obchodů</th>
            <th className="text-right pb-2">Win %</th>
            <th className="text-right pb-2">Ø R</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.key} className="border-t border-[#232735]">
              <td className="py-1.5 text-gray-200 truncate max-w-[140px]">{nameMap?.[b.key] || b.key}</td>
              <td className="text-right text-gray-400">{b.n}</td>
              <td className="text-right font-medium" style={{ color: b.win_rate != null && b.win_rate >= 50 ? "#4ade80" : "#9ca3af" }}>
                {b.win_rate != null ? `${b.win_rate}%` : "—"}
              </td>
              <td className="text-right font-medium" style={{ color: rColor(b.avg_r) }}>
                {b.avg_r != null ? `${b.avg_r > 0 ? "+" : ""}${b.avg_r}R` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* -------------------------------------------------------------- formulář */

const EMPTY = {
  instrument: "", direction: "long", traded_at: "", session: "",
  entry_price: "", exit_price: "", size: "", r_result: "", pnl: "",
  setup: "", notes: "", screenshot_url: "",
};
type FormState = typeof EMPTY;

function EntryForm({ initial, draft, meta, onClose, onSaved }: {
  initial: Entry | null; draft?: Partial<FormState> | null; meta?: AnalysisMeta | null;
  onClose: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState<FormState>(() => initial ? {
    instrument: initial.instrument ?? "",
    direction: initial.direction ?? "long",
    traded_at: toLocalInput(initial.traded_at),
    session: initial.session ?? "",
    entry_price: initial.entry_price?.toString() ?? "",
    exit_price: initial.exit_price?.toString() ?? "",
    size: initial.size?.toString() ?? "",
    r_result: initial.r_result?.toString() ?? "",
    pnl: initial.pnl?.toString() ?? "",
    setup: initial.setup ?? "",
    notes: initial.notes ?? "",
    screenshot_url: initial.screenshot_url ?? "",
  } : { ...EMPTY, traded_at: nowLocalInput(), ...(draft || {}) });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const set = (k: keyof FormState, v: string) => setF((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!f.instrument.trim()) { setErr("Instrument je povinný"); return; }
    setSaving(true); setErr(null);
    try {
      if (initial) await jFetch(`/${initial.id}`, { method: "PATCH", body: f });
      else await jFetch("", { method: "POST", body: f });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Uložení selhalo");
      setSaving(false);
    }
  };

  const field = "w-full rounded-lg bg-[#0f1117] border border-[#2a2d3a] px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-blue-600 focus:outline-none";
  const lab = "text-[10px] uppercase tracking-wider text-gray-500 mb-1 block";

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div className="bg-[#12141c] border border-[#2a2d3a] rounded-2xl max-w-lg w-full p-6 my-8" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white">{initial ? "Upravit obchod" : "Nový obchod"}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
        </div>

        {meta && (
          <div className="mb-4 rounded-lg border border-blue-900/40 bg-blue-950/30 px-3 py-2 text-[11px] text-blue-300 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold">🔎 AI analýza</span>
            <span className="text-blue-200">{meta.engine === "spark" ? "Spark" : "Claude"}{meta.model ? ` · ${meta.model}` : ""}</span>
            {meta.ms != null && <span>⏱ {(meta.ms / 1000).toFixed(1)} s</span>}
            {meta.total_tokens != null && (
              <span>🔢 {meta.total_tokens} tok{meta.in_tokens != null ? ` (${meta.in_tokens} in / ${meta.out_tokens} out)` : ""}</span>
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className={lab}>Instrument *</label>
            <input list="instr-list" className={field} value={f.instrument} placeholder="NQ, GOLD, YM…"
              onChange={(e) => set("instrument", e.target.value)} />
            <datalist id="instr-list"><option value="NQ" /><option value="GOLD" /><option value="YM" /><option value="ES" /><option value="DAX" /></datalist>
          </div>

          <div>
            <label className={lab}>Směr</label>
            <div className="flex gap-1.5">
              {(["long", "short"] as const).map((d) => (
                <button key={d} type="button" onClick={() => set("direction", d)}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium border transition-colors ${
                    f.direction === d
                      ? d === "long" ? "bg-green-950/50 text-green-300 border-green-800" : "bg-red-950/50 text-red-300 border-red-800"
                      : "bg-[#0f1117] text-gray-400 border-[#2a2d3a] hover:text-white"}`}>
                  {d === "long" ? "Long" : "Short"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className={lab}>Datum / čas</label>
            <input type="datetime-local" className={field} value={f.traded_at} onChange={(e) => set("traded_at", e.target.value)} />
          </div>

          <div>
            <label className={lab}>Entry</label>
            <input type="number" step="any" className={field} value={f.entry_price} onChange={(e) => set("entry_price", e.target.value)} />
          </div>
          <div>
            <label className={lab}>Exit</label>
            <input type="number" step="any" className={field} value={f.exit_price} onChange={(e) => set("exit_price", e.target.value)} />
          </div>

          <div>
            <label className={lab}>Výsledek (R)</label>
            <input type="number" step="any" className={field} value={f.r_result} placeholder="např. 2 nebo -1"
              onChange={(e) => set("r_result", e.target.value)} />
          </div>
          <div>
            <label className={lab}>P/L (body/měna)</label>
            <input type="number" step="any" className={field} value={f.pnl} onChange={(e) => set("pnl", e.target.value)} />
          </div>

          <div>
            <label className={lab}>Size</label>
            <input type="number" step="any" className={field} value={f.size} onChange={(e) => set("size", e.target.value)} />
          </div>
          <div>
            <label className={lab}>Session</label>
            <select className={field} value={f.session} onChange={(e) => set("session", e.target.value)}>
              {SESSION_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>

          <div className="col-span-2">
            <label className={lab}>Setup / strategie</label>
            <input className={field} value={f.setup} placeholder="např. ORB London, NPOC revisit…"
              onChange={(e) => set("setup", e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className={lab}>Screenshot (URL)</label>
            <input className={field} value={f.screenshot_url} placeholder="https://…"
              onChange={(e) => set("screenshot_url", e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className={lab}>Poznámka</label>
            <textarea className={`${field} min-h-[70px] resize-y`} value={f.notes}
              placeholder="Proč jsem do obchodu šel, co jsem se naučil…" onChange={(e) => set("notes", e.target.value)} />
          </div>
        </div>

        {err && <p className="text-sm text-red-400 mt-3">{err}</p>}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-gray-300 border border-[#2a2d3a] hover:text-white transition-colors">Zrušit</button>
          <button onClick={submit} disabled={saving}
            className="rounded-lg px-4 py-2 text-sm font-medium bg-[rgba(96,255,130,0.14)] text-[#8fffab] border border-[rgba(96,255,130,0.4)] hover:bg-[rgba(96,255,130,0.22)] transition-colors disabled:opacity-50">
            {saving ? "Ukládám…" : initial ? "Uložit změny" : "Přidat obchod"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------- AI analýza (vision) */

function extractedToForm(ex: Record<string, unknown>): Partial<FormState> {
  const s = (v: unknown) => (v === null || v === undefined || v === "" ? "" : String(v));
  const dir = String(ex.direction || "");
  return {
    instrument: s(ex.instrument),
    ...(dir === "long" || dir === "short" ? { direction: dir } : {}),
    entry_price: s(ex.entry_price),
    exit_price: s(ex.exit_price),
    r_result: s(ex.r_result),
    setup: s(ex.setup),
    notes: s(ex.notes),
    screenshot_url: s(ex.screenshot_url),
  };
}

function AnalyzeModal({ isAdmin, onClose, onExtracted }: {
  isAdmin: boolean; onClose: () => void;
  onExtracted: (draft: Partial<FormState>, meta: AnalysisMeta | null) => void;
}) {
  const [url, setUrl] = useState("");
  const [imgB64, setImgB64] = useState<string | null>(null);
  const [imgName, setImgName] = useState<string>("");
  const [engine, setEngine] = useState<"claude" | "spark">("claude");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImgName(file.name);
    const rd = new FileReader();
    rd.onload = () => setImgB64(rd.result as string);
    rd.readAsDataURL(file);
  };

  const run = async () => {
    if (!url.trim() && !imgB64) { setErr("Zadej TradingView odkaz nebo nahraj obrázek."); return; }
    if (engine === "spark" && !url.trim()) { setErr("Spark potřebuje TradingView odkaz (obrázek se neukládá)."); return; }
    setBusy(true); setErr(null); setStatus("Analyzuji graf…");
    try {
      const body: Record<string, unknown> = { engine };
      if (url.trim()) body.tradingview_url = url.trim();
      if (imgB64 && engine === "claude") body.image_base64 = imgB64;
      const res = await jFetch("/analyze", { method: "POST", body });
      if (res.status === "done") { onExtracted(extractedToForm(res.extracted), res.meta ?? null); return; }
      // spark → poll
      const jobId = res.job_id;
      setStatus("Spark zpracovává… (může chvíli trvat)");
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 2500));
        const st = await jFetch(`/analyze/${jobId}`);
        if (st.status === "done") { onExtracted(extractedToForm(st.extracted), st.meta ?? null); return; }
        if (st.status === "failed") throw new Error(st.error || "Spark analýza selhala");
      }
      throw new Error("Timeout — Spark neodpověděl. Běží na Sparku worker?");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Analýza selhala");
      setBusy(false); setStatus(null);
    }
  };

  const field = "w-full rounded-lg bg-[#0f1117] border border-[#2a2d3a] px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-blue-600 focus:outline-none";
  const lab = "text-[10px] uppercase tracking-wider text-gray-500 mb-1 block";

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 overflow-y-auto" onClick={busy ? undefined : onClose}>
      <div className="bg-[#12141c] border border-[#2a2d3a] rounded-2xl max-w-lg w-full p-6 my-8" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-bold text-white flex items-center gap-2"><Sparkles size={17} className="text-blue-400" /> Přidat z TradingView</h2>
          {!busy && <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>}
        </div>
        <p className="text-xs text-gray-500 mb-4">AI vytěží z grafu instrument, směr, entry/target a analýzu — pak si to zkontroluješ a uložíš.</p>

        <label className={lab}>TradingView odkaz (snapshot)</label>
        <input className={field} value={url} placeholder="https://www.tradingview.com/x/…"
          onChange={(e) => setUrl(e.target.value)} disabled={busy} />
        <p className="text-[10px] text-gray-600 mt-1">Na grafu ikona fotoaparátu → „Copy link to the chart image“.</p>

        {engine === "claude" && (
          <div className="mt-3">
            <label className={lab}>…nebo nahraj obrázek {imgName && <span className="text-gray-400 normal-case">— {imgName}</span>}</label>
            <input type="file" accept="image/*" onChange={onFile} disabled={busy}
              className="text-xs text-gray-400 file:mr-3 file:rounded-md file:border-0 file:bg-[#1e2536] file:px-3 file:py-1.5 file:text-gray-200 file:text-xs" />
            <p className="text-[10px] text-gray-600 mt-1">Obrázek se použije jen k analýze, neukládá se.</p>
          </div>
        )}

        {isAdmin && (
          <div className="mt-4">
            <label className={lab}>Engine (jen admin)</label>
            <div className="flex gap-1.5">
              {(["claude", "spark"] as const).map((k) => (
                <button key={k} type="button" onClick={() => setEngine(k)} disabled={busy}
                  className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium border transition-colors ${
                    engine === k ? "bg-[#1e2536] text-white border-[#2f3b55]"
                      : "bg-[#0f1117] text-gray-400 border-[#2a2d3a] hover:text-white"}`}>
                  {k === "claude" ? "Claude (cloud)" : "Spark (lokální)"}
                </button>
              ))}
            </div>
          </div>
        )}

        {status && <p className="text-sm text-blue-300 mt-4 flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-full border-2 border-blue-400 border-t-transparent animate-spin" /> {status}</p>}
        {err && <p className="text-sm text-red-400 mt-3">{err}</p>}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} disabled={busy} className="rounded-lg px-4 py-2 text-sm text-gray-300 border border-[#2a2d3a] hover:text-white transition-colors disabled:opacity-40">Zrušit</button>
          <button onClick={run} disabled={busy}
            className="rounded-lg px-4 py-2 text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors disabled:opacity-50 flex items-center gap-1.5">
            <Sparkles size={14} /> {busy ? "Analyzuji…" : "Analyzovat"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- CSV import */

function parseCSV(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cur = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; }
      else cur += c;
    } else if (c === '"') q = true;
    else if (c === "," || c === ";" || c === "\t") { row.push(cur); cur = ""; }
    else if (c === "\n") { row.push(cur); rows.push(row); row = []; cur = ""; }
    else if (c !== "\r") cur += c;
  }
  if (cur !== "" || row.length) { row.push(cur); rows.push(row); }
  return rows;
}

const COL_MAP: Record<string, string> = {
  instrument: "instrument", symbol: "instrument", ticker: "instrument", instr: "instrument",
  direction: "direction", side: "direction", type: "direction", smer: "direction", "směr": "direction",
  entry: "entry_price", entry_price: "entry_price", open: "entry_price", price: "entry_price", vstup: "entry_price",
  exit: "exit_price", exit_price: "exit_price", close: "exit_price", target: "exit_price", vystup: "exit_price", "výstup": "exit_price",
  size: "size", qty: "size", quantity: "size", contracts: "size", volume: "size", lot: "size", lots: "size",
  r: "r_result", rr: "r_result", r_result: "r_result", r_multiple: "r_result", "r-multiple": "r_result", vysledek: "r_result", "výsledek": "r_result",
  pnl: "pnl", profit: "pnl", pl: "pnl", "p/l": "pnl", "p&l": "pnl",
  date: "traded_at", time: "traded_at", datetime: "traded_at", traded_at: "traded_at", "date/time": "traded_at", datum: "traded_at", cas: "traded_at", "čas": "traded_at",
  session: "session", relace: "session", seance: "session",
  setup: "setup", strategy: "setup", strategie: "setup", tag: "setup",
  notes: "notes", note: "notes", comment: "notes", description: "notes", poznamka: "notes", "poznámka": "notes",
};
const normHeader = (h: string) => h.trim().toLowerCase().replace(/\s+/g, "_");

function ImportModal({ onClose, onDone }: { onClose: () => void; onDone: (created: number, errors: number) => void }) {
  const [rows, setRows] = useState<Record<string, string>[] | null>(null);
  const [mapped, setMapped] = useState<string[]>([]);
  const [ignored, setIgnored] = useState<string[]>([]);
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name); setErr(null); setRows(null);
    const rd = new FileReader();
    rd.onload = () => {
      try {
        const grid = parseCSV(String(rd.result)).filter((r) => r.some((c) => c.trim() !== ""));
        if (grid.length < 2) { setErr("CSV nemá data (chybí hlavička nebo řádky)."); return; }
        const hdr = grid[0].map((h) => h.trim());
        const fields = hdr.map((h) => COL_MAP[normHeader(h)] || null);
        setMapped(hdr.filter((_, i) => fields[i]));
        setIgnored(hdr.filter((_, i) => !fields[i]));
        const data = grid.slice(1).map((r) => {
          const o: Record<string, string> = {};
          fields.forEach((f, i) => { if (f && r[i] !== undefined && r[i].trim() !== "") o[f] = r[i].trim(); });
          return o;
        }).filter((o) => o.instrument);
        setRows(data);
        if (!data.length) setErr("Nenašel jsem řádky s instrumentem — je ve CSV sloupec instrument/symbol?");
      } catch { setErr("Nepodařilo se rozparsovat CSV."); }
    };
    rd.readAsText(file);
  };

  const doImport = async () => {
    if (!rows?.length) return;
    setBusy(true); setErr(null);
    try {
      const res = await jFetch("/import", { method: "POST", body: { rows } });
      onDone(res.created ?? 0, res.error_count ?? 0);
    } catch (e) { setErr(e instanceof Error ? e.message : "Import selhal"); setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 overflow-y-auto" onClick={busy ? undefined : onClose}>
      <div className="bg-[#12141c] border border-[#2a2d3a] rounded-2xl max-w-lg w-full p-6 my-8" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-bold text-white flex items-center gap-2"><Upload size={17} className="text-blue-400" /> Import CSV</h2>
          {!busy && <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>}
        </div>
        <p className="text-xs text-gray-500 mb-4">Nahraj CSV s obchody. Sloupce se namapují automaticky podle hlavičky.</p>

        <input type="file" accept=".csv,text/csv" onChange={onFile} disabled={busy}
          className="text-sm text-gray-400 file:mr-3 file:rounded-md file:border-0 file:bg-[#1e2536] file:px-3 file:py-1.5 file:text-gray-200 file:text-xs" />
        {fileName && <span className="text-xs text-gray-500 ml-2">{fileName}</span>}

        {rows && (
          <div className="mt-4 space-y-2 text-xs">
            <div className="text-gray-300">Nalezeno <b className="text-white">{rows.length}</b> obchodů.</div>
            <div className="flex flex-wrap gap-1.5">
              {mapped.map((h) => <span key={h} className="rounded bg-green-950/50 text-green-300 px-2 py-0.5">{h}</span>)}
              {ignored.map((h) => <span key={h} className="rounded bg-[#232735] text-gray-500 px-2 py-0.5 line-through">{h}</span>)}
            </div>
            {ignored.length > 0 && <div className="text-[10px] text-gray-600">Přeškrtnuté sloupce se ignorují (nerozpoznaná hlavička).</div>}
          </div>
        )}

        <details className="mt-4 text-[11px] text-gray-500">
          <summary className="cursor-pointer hover:text-gray-300">Jaké sloupce fungují?</summary>
          <div className="mt-2 leading-relaxed">
            <b className="text-gray-400">instrument</b> (symbol/ticker), <b className="text-gray-400">direction</b> (side/type — long/short i buy/sell),
            entry (open/price), exit (close/target), size (qty), r (rr), pnl (p/l), date (time/datetime),
            session, setup (strategy), notes (comment). Oddělovač , ; nebo tab.
          </div>
        </details>

        {err && <p className="text-sm text-red-400 mt-3">{err}</p>}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} disabled={busy} className="rounded-lg px-4 py-2 text-sm text-gray-300 border border-[#2a2d3a] hover:text-white transition-colors disabled:opacity-40">Zrušit</button>
          <button onClick={doImport} disabled={busy || !rows?.length}
            className="rounded-lg px-4 py-2 text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors disabled:opacity-50 flex items-center gap-1.5">
            <Upload size={14} /> {busy ? "Importuji…" : `Importovat${rows?.length ? ` (${rows.length})` : ""}`}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- page */

export default function DenikPage() {
  const { user, loading: authLoading } = useAuth();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Entry | null>(null);
  const [analyzeOpen, setAnalyzeOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [draft, setDraft] = useState<Partial<FormState> | null>(null);
  const [lastMeta, setLastMeta] = useState<AnalysisMeta | null>(null);

  const reload = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [list, st] = await Promise.all([jFetch(""), jFetch("/stats")]);
      setEntries((list as { entries: Entry[] }).entries);
      setStats(st as Stats);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Načtení selhalo");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && user) reload();
    else if (!authLoading && !user) setLoading(false);
  }, [authLoading, user, reload]);

  const openNew = () => { setEditing(null); setDraft(null); setLastMeta(null); setFormOpen(true); };
  const openEdit = (e: Entry) => { setEditing(e); setDraft(null); setLastMeta(null); setFormOpen(true); };
  const onSaved = () => { setFormOpen(false); setEditing(null); setDraft(null); setLastMeta(null); reload(); };
  const onExtracted = (d: Partial<FormState>, meta: AnalysisMeta | null) => {
    setAnalyzeOpen(false); setEditing(null); setDraft(d);
    setLastMeta(user?.is_admin ? meta : null); setFormOpen(true);
  };
  const onImported = (created: number, errors: number) => {
    setImportOpen(false); reload();
    alert(`Importováno ${created} obchodů${errors ? `, ${errors} přeskočeno (chybějící instrument apod.)` : ""}.`);
  };
  const remove = async (e: Entry) => {
    if (!confirm(`Smazat obchod ${e.instrument} z ${fmtDate(e.traded_at)}?`)) return;
    try { await jFetch(`/${e.id}`, { method: "DELETE" }); reload(); }
    catch (err) { alert(err instanceof Error ? err.message : "Smazání selhalo"); }
  };

  const t = stats?.totals;
  const pnlLabel = useMemo(() => {
    if (!t) return "";
    return t.sum_pnl != null ? `Σ P/L ${t.sum_pnl}` : "";
  }, [t]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-950/60 border border-blue-900/50">
              <NotebookPen size={16} className="text-blue-400" />
            </span>
            <h1 className="text-2xl font-bold text-white">Obchodní deník</h1>
          </div>
          <p className="text-sm text-gray-400 mt-1">Zaznamenávej obchody a sleduj, co ti reálně funguje</p>
        </div>
        {user && (
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={() => setAnalyzeOpen(true)}
              className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium bg-blue-600/90 text-white border border-blue-500 hover:bg-blue-500 transition-colors">
              <Sparkles size={15} /> Z TradingView (AI)
            </button>
            <button onClick={() => setImportOpen(true)}
              className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium bg-[#151823] text-gray-300 border border-[#2a2d3a] hover:text-white transition-colors">
              <Upload size={15} /> Import CSV
            </button>
            <button onClick={openNew}
              className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium bg-[rgba(96,255,130,0.14)] text-[#8fffab] border border-[rgba(96,255,130,0.4)] hover:bg-[rgba(96,255,130,0.22)] transition-colors">
              <Plus size={15} /> Přidat obchod
            </button>
          </div>
        )}
      </div>

      {!authLoading && !user && (
        <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-8 text-center">
          <p className="text-gray-300">Deník je dostupný po přihlášení.</p>
          <div className="flex justify-center gap-3 mt-4">
            <Link href="/prihlaseni" className="rounded-lg px-4 py-2 text-sm bg-[#1e2536] text-white border border-[#2f3b55] hover:border-gray-500 transition-colors">Přihlásit se</Link>
            <Link href="/registrace" className="rounded-lg px-4 py-2 text-sm text-[#8fffab] border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.10)] hover:bg-[rgba(96,255,130,0.18)] transition-colors">Registrovat</Link>
          </div>
        </div>
      )}

      {error && <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-4 text-sm text-yellow-300">{error}</div>}

      {user && loading && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-24 rounded-xl bg-[#151823] animate-pulse border border-[#2a2d3a]" />)}
        </div>
      )}

      {user && !loading && t && (
        <>
          {/* souhrn */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Obchodů" value={String(t.trades)} sub={pnlLabel || undefined} />
            <StatCard label="Win rate" value={t.win_rate != null ? `${t.win_rate}%` : "—"}
              sub={t.decided ? `${t.wins}W / ${t.losses}L${t.breakeven ? ` / ${t.breakeven}BE` : ""}` : "chybí výsledky"}
              color={t.win_rate != null && t.win_rate >= 50 ? "#4ade80" : undefined} />
            <StatCard label="Ø R (expektance)" value={t.avg_r != null ? `${t.avg_r > 0 ? "+" : ""}${t.avg_r}R` : "—"}
              color={rColor(t.avg_r)} />
            <StatCard label="Σ R" value={t.sum_r != null ? `${t.sum_r > 0 ? "+" : ""}${t.sum_r}R` : "—"}
              sub={t.best_r != null ? `nej ${t.best_r} · nejh ${t.worst_r}` : undefined} color={rColor(t.sum_r)} />
          </div>

          {/* rozklad */}
          {t.trades > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <BucketTable title="Podle setupu" rows={stats!.by_setup} />
              <BucketTable title="Podle session" rows={stats!.by_session} nameMap={SESSION_NAME} />
              <BucketTable title="Podle instrumentu" rows={stats!.by_instrument} />
            </div>
          )}

          {/* seznam obchodů */}
          {entries.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[#2a2d3a] bg-[#12141c] p-10 text-center">
              <TrendingUp size={28} className="mx-auto text-gray-600 mb-3" />
              <p className="text-gray-300 font-medium">Zatím žádné obchody</p>
              <p className="text-sm text-gray-500 mt-1">Přidej první záznam tlačítkem „Přidat obchod“ nahoře.</p>
            </div>
          ) : (
            <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[720px]">
                  <thead>
                    <tr className="text-gray-500 text-[10px] uppercase bg-[#181b26]">
                      <th className="text-left px-3 py-2.5">Datum</th>
                      <th className="text-left px-3 py-2.5">Instrument</th>
                      <th className="text-left px-3 py-2.5">Směr</th>
                      <th className="text-right px-3 py-2.5">R</th>
                      <th className="text-left px-3 py-2.5">Setup</th>
                      <th className="text-left px-3 py-2.5">Session</th>
                      <th className="text-left px-3 py-2.5">Pozn.</th>
                      <th className="px-3 py-2.5"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((e) => {
                      const oc = outcomeOf(e);
                      return (
                        <tr key={e.id} className="border-t border-[#232735] hover:bg-[#181b26]/50">
                          <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap">{fmtDate(e.traded_at)}</td>
                          <td className="px-3 py-2.5 font-medium text-gray-100">{e.instrument}</td>
                          <td className="px-3 py-2.5">
                            <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${e.direction === "long" ? "bg-green-950/60 text-green-300" : "bg-red-950/60 text-red-300"}`}>
                              {e.direction === "long" ? "Long" : "Short"}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-right font-semibold" style={{ color: rColor(oc) }}>
                            {e.r_result != null ? `${e.r_result > 0 ? "+" : ""}${e.r_result}R` : e.pnl != null ? `${e.pnl > 0 ? "+" : ""}${e.pnl}` : "—"}
                          </td>
                          <td className="px-3 py-2.5 text-gray-300 max-w-[160px] truncate">{e.setup || "—"}</td>
                          <td className="px-3 py-2.5 text-gray-400">{e.session ? (SESSION_NAME[e.session] || e.session) : "—"}</td>
                          <td className="px-3 py-2.5 text-gray-500 max-w-[180px] truncate" title={e.notes || ""}>
                            {e.screenshot_url && (
                              <a href={e.screenshot_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 mr-2">
                                <ExternalLink size={12} /> img
                              </a>
                            )}
                            {e.notes || (e.screenshot_url ? "" : "—")}
                          </td>
                          <td className="px-3 py-2.5 whitespace-nowrap text-right">
                            <button onClick={() => openEdit(e)} className="text-gray-500 hover:text-blue-400 p-1" title="Upravit"><Pencil size={14} /></button>
                            <button onClick={() => remove(e)} className="text-gray-500 hover:text-red-400 p-1" title="Smazat"><Trash2 size={14} /></button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {analyzeOpen && <AnalyzeModal isAdmin={!!user?.is_admin} onClose={() => setAnalyzeOpen(false)} onExtracted={onExtracted} />}
      {importOpen && <ImportModal onClose={() => setImportOpen(false)} onDone={onImported} />}
      {formOpen && <EntryForm initial={editing} draft={draft} meta={lastMeta} onClose={() => { setFormOpen(false); setEditing(null); setDraft(null); setLastMeta(null); }} onSaved={onSaved} />}
    </div>
  );
}
