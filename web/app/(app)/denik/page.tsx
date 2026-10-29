"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { NotebookPen, Plus, Pencil, Trash2, X, ExternalLink, TrendingUp, Sparkles, Upload, Tags, AlertTriangle, ChevronLeft, ChevronRight, CalendarDays } from "lucide-react";
import { authToken, useAuth } from "@/lib/auth";
import Link from "next/link";

/* ---------------------------------------------------------------- typy */

interface Entry {
  id: number;
  instrument: string;
  direction: "long" | "short";
  entry_price: number | null;
  exit_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  outcome: "win" | "loss" | "be" | null;
  size: number | null;
  r_result: number | null;
  pnl: number | null;
  traded_at: string | null;
  session: string | null;
  setup: string | null;
  notes: string | null;
  screenshot_url: string | null;
  strategy_id: number | null;
  tag_ids: number[];
  mistake_ids: number[];
  loss_reason: string | null;
  created_at: string | null;
}
type TagKind = "setup" | "timeframe" | "mistake";
interface Tag { id: number; kind: TagKind; name: string }
interface Strategy { id: number; name: string; description: string | null; tag_ids: number[] }
interface TagData { tags: Tag[]; strategies: Strategy[] }
interface Bucket { key: string; n: number; win_rate: number | null; avg_r: number | null }
interface MistakeBucket { key: string; n: number; r_lost: number }
interface Stats {
  totals: {
    trades: number; decided: number; wins: number; losses: number; breakeven: number;
    win_rate: number | null; avg_r: number | null; sum_r: number | null;
    best_r: number | null; worst_r: number | null; sum_pnl: number | null;
  };
  by_setup: Bucket[];
  by_session: Bucket[];
  by_instrument: Bucket[];
  by_strategy: Bucket[];
  by_tag: Bucket[];
  by_timeframe: Bucket[];
  by_combo: Bucket[];
  by_mistake: MistakeBucket[];
  losses: { total: number; explained: number };
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
  // explicitní výsledek (Win/Loss přepínač) má přednost před znaménkem R/P&L
  if (e.outcome === "win") return 1;
  if (e.outcome === "loss") return -1;
  if (e.outcome === "be") return 0;
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

function MistakeTable({ rows, losses }: { rows: MistakeBucket[]; losses: { total: number; explained: number } }) {
  if (!losses.total) return null;
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <h3 className="text-sm font-semibold text-white mb-1 flex items-center gap-1.5">
        <AlertTriangle size={14} className="text-orange-400" /> Proč obchody nevycházejí
      </h3>
      <p className="text-[11px] text-gray-500 mb-3">
        Důvod máš vyplněný u {losses.explained} z {losses.total} ztrát
        {losses.explained < losses.total ? " — doplň ho u zbytku, ať je přehled úplný." : "."}
      </p>
      {rows.length > 0 ? (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 text-[10px] uppercase">
              <th className="text-left pb-2">Chyba</th>
              <th className="text-right pb-2">Kolikrát</th>
              <th className="text-right pb-2">Stálo tě</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.key} className="border-t border-[#232735]">
                <td className="py-1.5 text-gray-200">{m.key}</td>
                <td className="text-right text-gray-400">{m.n}×</td>
                <td className="text-right font-medium" style={{ color: rColor(m.r_lost) }}>{m.r_lost ? `${m.r_lost}R` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="text-xs text-gray-500">Zatím žádné označené chyby.</p>}
    </div>
  );
}

function Chip({ on, label, onClick, tone = "blue" }: { on: boolean; label: string; onClick: () => void; tone?: "blue" | "orange" }) {
  const onCls = tone === "orange" ? "bg-orange-950/50 text-orange-300 border-orange-800" : "bg-blue-950/50 text-blue-300 border-blue-800";
  return (
    <button type="button" onClick={onClick}
      className={`rounded-full px-2.5 py-1 text-xs border transition-colors ${on ? onCls : "bg-[#0f1117] text-gray-400 border-[#2a2d3a] hover:text-white"}`}>
      {label}
    </button>
  );
}

const KIND_LABEL: Record<TagKind, string> = { setup: "Setup", timeframe: "Timeframe", mistake: "Chyby (důvod ztráty)" };
const toggle = (arr: number[], id: number) => (arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);

/* -------------------------------------------------------------- kalendář */

const pad2 = (n: number) => String(n).padStart(2, "0");
/** Místní den obchodu (YYYY-MM-DD) — podle času, který uživatel zadal. */
function dayKey(s: string | null): string | null {
  if (!s) return null;
  const d = new Date(s);
  if (isNaN(d.getTime())) return null;
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}
interface DayAgg { n: number; wins: number; decided: number; sumR: number | null; sumPnl: number | null }
function aggregate(items: Entry[]): DayAgg {
  const a: DayAgg = { n: 0, wins: 0, decided: 0, sumR: null, sumPnl: null };
  for (const e of items) {
    a.n++;
    const o = outcomeOf(e);
    if (o !== null) { a.decided++; if (o > 0) a.wins++; }
    if (e.r_result != null) a.sumR = (a.sumR ?? 0) + e.r_result;
    if (e.pnl != null) a.sumPnl = (a.sumPnl ?? 0) + e.pnl;
  }
  return a;
}
/** Hlavní číslo dne: součet R; když R chybí, součet P/L. */
function dayValue(a: DayAgg): { v: number | null; label: string } {
  const r2 = (x: number) => Math.round(x * 100) / 100;
  if (a.sumR != null) return { v: a.sumR, label: `${a.sumR > 0 ? "+" : ""}${r2(a.sumR)}R` };
  if (a.sumPnl != null) return { v: a.sumPnl, label: `${a.sumPnl > 0 ? "+" : ""}${r2(a.sumPnl)}` };
  if (a.decided) { const net = 2 * a.wins - a.decided; return { v: net, label: `${a.wins}W/${a.decided - a.wins}L` }; }
  return { v: null, label: "—" };
}
function dayStyle(v: number | null): React.CSSProperties {
  if (v == null || v === 0) return { background: "#1a1d27", borderColor: "#2a2d3a" };
  return v > 0
    ? { background: "rgba(34,197,94,0.14)", borderColor: "rgba(34,197,94,0.45)" }
    : { background: "rgba(239,68,68,0.14)", borderColor: "rgba(239,68,68,0.45)" };
}
const WEEKDAYS = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"];

function JournalCalendar({ entries, selected, onSelect }: {
  entries: Entry[]; selected: string | null; onSelect: (day: string | null) => void;
}) {
  // Výchozí měsíc = měsíc posledního obchodu (jinak aktuální)
  const [month, setMonth] = useState(() => {
    const last = entries.map((e) => dayKey(e.traded_at)).filter(Boolean).sort().pop();
    const d = last ? new Date(`${last}T12:00:00`) : new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const byDay = useMemo(() => {
    const m = new Map<string, Entry[]>();
    for (const e of entries) { const k = dayKey(e.traded_at); if (k) m.set(k, [...(m.get(k) || []), e]); }
    return m;
  }, [entries]);

  const y = month.getFullYear(), mo = month.getMonth();
  const first = (new Date(y, mo, 1).getDay() + 6) % 7;        // pondělí = 0
  const days = new Date(y, mo + 1, 0).getDate();
  const cells: (number | null)[] = [...Array(first).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const weeks = Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7));
  const key = (d: number) => `${y}-${pad2(mo + 1)}-${pad2(d)}`;
  const monthItems = Array.from(byDay.entries()).filter(([k]) => k.startsWith(`${y}-${pad2(mo + 1)}`)).flatMap(([, v]) => v);
  const mAgg = aggregate(monthItems);
  const mVal = dayValue(mAgg);
  const tradingDays = new Set(monthItems.map((e) => dayKey(e.traded_at))).size;
  const greenDays = Array.from(byDay.entries()).filter(([k, v]) => k.startsWith(`${y}-${pad2(mo + 1)}`) && (dayValue(aggregate(v)).v ?? 0) > 0).length;
  const shift = (n: number) => setMonth(new Date(y, mo + n, 1));
  const todayKey = dayKey(new Date().toISOString());

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <CalendarDays size={16} className="text-blue-400" />
          <button onClick={() => shift(-1)} className="p-1 text-gray-400 hover:text-white" aria-label="Předchozí měsíc"><ChevronLeft size={16} /></button>
          <h3 className="text-sm font-semibold text-white w-32 text-center capitalize">
            {month.toLocaleDateString("cs", { month: "long", year: "numeric" })}
          </h3>
          <button onClick={() => shift(1)} className="p-1 text-gray-400 hover:text-white" aria-label="Další měsíc"><ChevronRight size={16} /></button>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-400">
          <span>Měsíc: <b style={{ color: rColor(mVal.v) }}>{mVal.label}</b></span>
          <span>{mAgg.n} obchodů{mAgg.decided ? ` · win ${Math.round((100 * mAgg.wins) / mAgg.decided)} %` : ""}</span>
          {tradingDays > 0 && <span>{greenDays}/{tradingDays} dní v plusu</span>}
        </div>
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[560px] grid grid-cols-[repeat(7,minmax(0,1fr))_minmax(0,0.9fr)] gap-1.5">
          {WEEKDAYS.map((w) => <div key={w} className="text-[10px] uppercase text-gray-500 text-center pb-1">{w}</div>)}
          <div className="text-[10px] uppercase text-gray-500 text-center pb-1">Týden</div>
          {weeks.map((wk, wi) => {
            const wItems = wk.filter((d): d is number => d != null).flatMap((d) => byDay.get(key(d)) || []);
            const wAgg = aggregate(wItems);
            const wVal = dayValue(wAgg);
            return (
              <div key={wi} className="contents">
                {wk.map((d, di) => {
                  if (d == null) return <div key={di} />;
                  const k = key(d);
                  const items = byDay.get(k);
                  const a = items ? aggregate(items) : null;
                  const val = a ? dayValue(a) : null;
                  const isSel = selected === k;
                  return (
                    <button key={di} type="button" disabled={!items}
                      onClick={() => onSelect(isSel ? null : k)}
                      title={a ? `${a.n} obchodů · ${a.wins}W / ${a.decided - a.wins}L` : undefined}
                      className={`h-[72px] rounded-lg border p-1.5 text-left flex flex-col transition-colors ${items ? "hover:brightness-125 cursor-pointer" : "cursor-default"} ${isSel ? "ring-2 ring-blue-500" : ""}`}
                      style={a ? dayStyle(val!.v) : { background: "#12141c", borderColor: "#1f2230" }}>
                      <span className={`text-[10px] ${k === todayKey ? "text-blue-300 font-bold" : "text-gray-500"}`}>{d}</span>
                      {a && (
                        <>
                          <span className="text-sm font-bold mt-auto leading-tight" style={{ color: rColor(val!.v) }}>{val!.label}</span>
                          <span className="text-[10px] text-gray-400 leading-tight">
                            {a.n} {a.n === 1 ? "obchod" : a.n < 5 ? "obchody" : "obchodů"}{a.decided ? ` · ${Math.round((100 * a.wins) / a.decided)} %` : ""}
                          </span>
                        </>
                      )}
                    </button>
                  );
                })}
                <div className="h-[72px] rounded-lg border border-dashed border-[#2a2d3a] p-1.5 flex flex-col justify-end">
                  {wAgg.n > 0 ? (
                    <>
                      <span className="text-sm font-bold leading-tight" style={{ color: rColor(wVal.v) }}>{wVal.label}</span>
                      <span className="text-[10px] text-gray-500 leading-tight">{wAgg.n} obch.{wAgg.decided ? ` · ${Math.round((100 * wAgg.wins) / wAgg.decided)} %` : ""}</span>
                    </>
                  ) : <span className="text-[10px] text-gray-600">—</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <p className="mt-2 text-[10px] text-gray-600">Číslo dne = součet R (bez R součet P/L). Procento = win rate dne. Kliknutím na den zobrazíš jeho obchody níže.</p>
    </div>
  );
}

/* -------------------------------------------------------------- formulář */

const EMPTY = {
  instrument: "", direction: "long", traded_at: "", session: "",
  entry_price: "", exit_price: "", stop_price: "", target_price: "", outcome: "",
  size: "", r_result: "", pnl: "",
  setup: "", notes: "", screenshot_url: "",
};
type FormState = typeof EMPTY;

/** Z Entry/SL/TP a výsledku dopočítá Exit a R (win: exit=TP, R=|TP−entry|/|entry−SL|;
 *  loss: exit=SL, R=−1). Chybí-li vstupy, vrátí prázdné — nic nevymýšlí. */
function resultFromLevels(f: FormState, outcome: string): { exit_price: string; r_result: string } {
  const n = (v: string) => (v.trim() === "" || isNaN(Number(v)) ? null : Number(v));
  const entry = n(f.entry_price), sl = n(f.stop_price), tp = n(f.target_price);
  if (outcome === "loss") return { exit_price: sl != null ? String(sl) : "", r_result: sl != null ? "-1" : "" };
  if (outcome === "win") {
    const r = entry != null && sl != null && tp != null && entry !== sl
      ? String(Math.round((Math.abs(tp - entry) / Math.abs(entry - sl)) * 100) / 100) : "";
    return { exit_price: tp != null ? String(tp) : "", r_result: r };
  }
  return { exit_price: f.exit_price, r_result: f.r_result };
}

function EntryForm({ initial, draft, meta, tagData, onClose, onSaved, onManageTags }: {
  initial: Entry | null; draft?: Partial<FormState> | null; meta?: AnalysisMeta | null;
  tagData: TagData; onClose: () => void; onSaved: () => void; onManageTags: () => void;
}) {
  const [strategyId, setStrategyId] = useState<number | null>(initial?.strategy_id ?? null);
  const [tagIds, setTagIds] = useState<number[]>(initial?.tag_ids ?? []);
  const [mistakeIds, setMistakeIds] = useState<number[]>(initial?.mistake_ids ?? []);
  const [lossReason, setLossReason] = useState(initial?.loss_reason ?? "");
  // Výběr strategie předvyplní její tagy (přidá k už zaškrtnutým; jednotlivé jde pak odškrtnout)
  const pickStrategy = (v: string) => {
    const id = v ? Number(v) : null;
    setStrategyId(id);
    const st = tagData.strategies.find((x) => x.id === id);
    if (st) setTagIds((cur) => [...cur, ...st.tag_ids.filter((t) => !cur.includes(t))]);
  };
  const tagsOf = (k: TagKind) => tagData.tags.filter((t) => t.kind === k);
  const [f, setF] = useState<FormState>(() => initial ? {
    instrument: initial.instrument ?? "",
    direction: initial.direction ?? "long",
    traded_at: toLocalInput(initial.traded_at),
    session: initial.session ?? "",
    entry_price: initial.entry_price?.toString() ?? "",
    exit_price: initial.exit_price?.toString() ?? "",
    stop_price: initial.stop_price?.toString() ?? "",
    target_price: initial.target_price?.toString() ?? "",
    outcome: initial.outcome ?? "",
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
  // Přepnutí výsledku Win/Loss (znovu kliknutí = zrušit) přepočítá Exit a R ze SL/TP
  const setOutcome = (o: string) => setF((p) => {
    const next = p.outcome === o ? "" : o;
    return { ...p, outcome: next, ...(next ? resultFromLevels(p, next) : {}) };
  });
  // Změna Entry/SL/TP při zvoleném výsledku přepočítá Exit/R (dokud je Win/Loss zapnuté)
  const setLevel = (k: "entry_price" | "stop_price" | "target_price", v: string) => setF((p) => {
    const q = { ...p, [k]: v };
    return p.outcome ? { ...q, ...resultFromLevels(q, p.outcome) } : q;
  });

  const submit = async () => {
    if (!f.instrument.trim()) { setErr("Instrument je povinný"); return; }
    setSaving(true); setErr(null);
    try {
      const isLoss = f.outcome === "loss" || (f.r_result.trim() !== "" && Number(f.r_result) < 0);
      const body = {
        ...f, strategy_id: strategyId, tag_ids: tagIds,
        mistake_ids: isLoss ? mistakeIds : [], loss_reason: isLoss ? lossReason : "",
      };
      if (initial) await jFetch(`/${initial.id}`, { method: "PATCH", body });
      else await jFetch("", { method: "POST", body });
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
            <input type="number" step="any" className={field} value={f.entry_price} onChange={(e) => setLevel("entry_price", e.target.value)} />
          </div>
          <div>
            <label className={lab}>Exit (skutečný)</label>
            <input type="number" step="any" className={field} value={f.exit_price} onChange={(e) => set("exit_price", e.target.value)} />
          </div>

          <div>
            <label className={lab}>SL (stop)</label>
            <input type="number" step="any" className={field} value={f.stop_price} onChange={(e) => setLevel("stop_price", e.target.value)} />
          </div>
          <div>
            <label className={lab}>TP (cíl)</label>
            <input type="number" step="any" className={field} value={f.target_price} onChange={(e) => setLevel("target_price", e.target.value)} />
          </div>

          <div className="col-span-2">
            <label className={lab}>Výsledek obchodu</label>
            <div className="flex gap-1.5">
              {([["win", "Win"], ["loss", "Loss"]] as const).map(([o, l]) => (
                <button key={o} type="button" onClick={() => setOutcome(o)}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium border transition-colors ${
                    f.outcome === o
                      ? o === "win" ? "bg-green-950/50 text-green-300 border-green-800" : "bg-red-950/50 text-red-300 border-red-800"
                      : "bg-[#0f1117] text-gray-400 border-[#2a2d3a] hover:text-white"}`}>
                  {l}
                </button>
              ))}
            </div>
            <p className="mt-1 text-[10px] text-gray-600">Win → Exit = TP a R podle SL/TP; Loss → Exit = SL a −1R. Dalším kliknutím zrušíš.</p>
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

          <div className="col-span-2 rounded-xl border border-[#2a2d3a] bg-[#0f1117]/60 p-3 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-200">Za jaké situace jsi obchod vzal</span>
              <button type="button" onClick={onManageTags} className="text-[11px] text-blue-400 hover:text-blue-300 flex items-center gap-1">
                <Tags size={12} /> Upravit tagy a strategie
              </button>
            </div>
            <div>
              <label className={lab}>Strategie</label>
              <select className={field} value={strategyId ?? ""} onChange={(e) => pickStrategy(e.target.value)}>
                <option value="">— bez strategie (jen tagy) —</option>
                {tagData.strategies.map((st) => <option key={st.id} value={st.id}>{st.name}</option>)}
              </select>
            </div>
            {(["setup", "timeframe"] as const).map((k) => (
              <div key={k}>
                <label className={lab}>{KIND_LABEL[k]}</label>
                <div className="flex flex-wrap gap-1.5">
                  {tagsOf(k).map((t) => <Chip key={t.id} on={tagIds.includes(t.id)} label={t.name} onClick={() => setTagIds((c) => toggle(c, t.id))} />)}
                </div>
              </div>
            ))}
            {(initial?.setup || draft?.setup) && (
              <div>
                <label className={lab}>Setup (původní volný popis)</label>
                <input className={field} value={f.setup} onChange={(e) => set("setup", e.target.value)} />
              </div>
            )}
          </div>

          {(f.outcome === "loss" || (f.r_result.trim() !== "" && Number(f.r_result) < 0)) && (
            <div className="col-span-2 rounded-xl border border-orange-900/50 bg-orange-950/20 p-3 space-y-2">
              <span className="text-xs font-semibold text-orange-300 flex items-center gap-1.5"><AlertTriangle size={13} /> Proč obchod nevyšel?</span>
              <div className="flex flex-wrap gap-1.5">
                {tagsOf("mistake").map((t) => <Chip key={t.id} tone="orange" on={mistakeIds.includes(t.id)} label={t.name} onClick={() => setMistakeIds((c) => toggle(c, t.id))} />)}
              </div>
              <textarea className={`${field} min-h-[56px] resize-y`} value={lossReason}
                placeholder="Vlastními slovy: co jsem udělal jinak než podle plánu… (nebo „obchod byl podle plánu, jen nevyšel“)"
                onChange={(e) => setLossReason(e.target.value)} />
            </div>
          )}
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

/* ------------------------------------------------- správa tagů a strategií */

function TagsModal({ data, onClose, onChanged }: { data: TagData; onClose: () => void; onChanged: () => Promise<void> }) {
  const [newName, setNewName] = useState<Record<TagKind, string>>({ setup: "", timeframe: "", mistake: "" });
  const [err, setErr] = useState<string | null>(null);
  const [st, setSt] = useState<{ id: number | null; name: string; description: string; tag_ids: number[] } | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try { await fn(); await onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : "Akce selhala"); }
  };
  const addTag = (k: TagKind) => {
    const name = newName[k].trim();
    if (!name) return;
    run(async () => { await jFetch("/tags", { method: "POST", body: { kind: k, name } }); setNewName((p) => ({ ...p, [k]: "" })); });
  };
  const renameTag = (t: Tag) => {
    const name = prompt("Nový název tagu", t.name);
    if (name && name.trim() !== t.name) run(() => jFetch(`/tags/${t.id}`, { method: "PATCH", body: { name } }));
  };
  const deleteTag = (t: Tag) => {
    if (confirm(`Smazat tag „${t.name}“? Odebere se ze všech obchodů a strategií.`)) run(() => jFetch(`/tags/${t.id}`, { method: "DELETE" }));
  };
  const saveStrategy = () => {
    if (!st) return;
    run(async () => {
      const body = { name: st.name, description: st.description, tag_ids: st.tag_ids };
      if (st.id) await jFetch(`/strategies/${st.id}`, { method: "PATCH", body });
      else await jFetch("/strategies", { method: "POST", body });
      setSt(null);
    });
  };
  const deleteStrategy = (x: Strategy) => {
    if (confirm(`Smazat strategii „${x.name}“? Obchody zůstanou, jen bez strategie.`)) run(() => jFetch(`/strategies/${x.id}`, { method: "DELETE" }));
  };
  const tagName = (id: number) => data.tags.find((t) => t.id === id)?.name;
  const field = "w-full rounded-lg bg-[#0f1117] border border-[#2a2d3a] px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-blue-600 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div className="bg-[#12141c] border border-[#2a2d3a] rounded-2xl max-w-2xl w-full p-6 my-8 space-y-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-white flex items-center gap-2"><Tags size={17} className="text-blue-400" /> Tagy a strategie</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}

        {/* strategie */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-white">Strategie</h3>
            {!st && (
              <button onClick={() => setSt({ id: null, name: "", description: "", tag_ids: [] })}
                className="text-xs text-[#8fffab] flex items-center gap-1"><Plus size={13} /> Nová strategie</button>
            )}
          </div>
          <p className="text-[11px] text-gray-500 mb-3">Strategie je pojmenovaná kombinace tagů (např. „Sweep + iFVG“ = Liquidity, iFVG, M5). U obchodu ji vybereš jedním klikem.</p>
          {st && (
            <div className="rounded-xl border border-[#2f3b55] bg-[#0f1117] p-3 space-y-2 mb-3">
              <input className={field} value={st.name} placeholder="Název strategie" maxLength={60} onChange={(e) => setSt({ ...st, name: e.target.value })} />
              <textarea className={`${field} min-h-[50px]`} value={st.description} placeholder="Pravidla vstupu (volitelné)…" onChange={(e) => setSt({ ...st, description: e.target.value })} />
              {(["setup", "timeframe"] as const).map((k) => (
                <div key={k} className="flex flex-wrap gap-1.5 items-center">
                  <span className="text-[10px] uppercase tracking-wider text-gray-500 w-20">{KIND_LABEL[k]}</span>
                  {data.tags.filter((t) => t.kind === k).map((t) => (
                    <Chip key={t.id} on={st.tag_ids.includes(t.id)} label={t.name} onClick={() => setSt({ ...st, tag_ids: toggle(st.tag_ids, t.id) })} />
                  ))}
                </div>
              ))}
              <div className="flex justify-end gap-2 pt-1">
                <button onClick={() => setSt(null)} className="rounded-lg px-3 py-1.5 text-xs text-gray-300 border border-[#2a2d3a]">Zrušit</button>
                <button onClick={saveStrategy} disabled={!st.name.trim()} className="rounded-lg px-3 py-1.5 text-xs bg-blue-600 text-white disabled:opacity-40">Uložit strategii</button>
              </div>
            </div>
          )}
          <div className="space-y-1.5">
            {data.strategies.length === 0 && !st && <p className="text-xs text-gray-500">Zatím žádná strategie.</p>}
            {data.strategies.map((x) => (
              <div key={x.id} className="flex items-start justify-between gap-2 rounded-lg border border-[#232735] px-3 py-2">
                <div className="min-w-0">
                  <div className="text-sm text-gray-100">{x.name}</div>
                  <div className="text-[11px] text-gray-500">{x.tag_ids.map(tagName).filter(Boolean).join(" · ") || "bez tagů"}</div>
                </div>
                <div className="shrink-0">
                  <button onClick={() => setSt({ id: x.id, name: x.name, description: x.description ?? "", tag_ids: x.tag_ids })} className="text-gray-500 hover:text-blue-400 p-1" title="Upravit"><Pencil size={13} /></button>
                  <button onClick={() => deleteStrategy(x)} className="text-gray-500 hover:text-red-400 p-1" title="Smazat"><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* tagy */}
        {(["setup", "timeframe", "mistake"] as const).map((k) => (
          <section key={k}>
            <h3 className="text-sm font-semibold text-white mb-2">{KIND_LABEL[k]}</h3>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {data.tags.filter((t) => t.kind === k).map((t) => (
                <span key={t.id} className="inline-flex items-center gap-1 rounded-full border border-[#2a2d3a] bg-[#0f1117] pl-2.5 pr-1 py-0.5 text-xs text-gray-200">
                  <button onClick={() => renameTag(t)} title="Přejmenovat" className="hover:text-blue-300">{t.name}</button>
                  <button onClick={() => deleteTag(t)} title="Smazat" className="text-gray-600 hover:text-red-400"><X size={12} /></button>
                </span>
              ))}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); addTag(k); }} className="flex gap-2">
              <input className={`${field} py-1.5`} value={newName[k]} maxLength={40}
                placeholder={k === "mistake" ? "Nová chyba, např. „Obchodoval jsem unavený“" : k === "timeframe" ? "např. M3" : "např. Breaker, SMT, Judas swing"}
                onChange={(e) => setNewName((p) => ({ ...p, [k]: e.target.value }))} />
              <button type="submit" disabled={!newName[k].trim()} className="rounded-lg px-3 text-xs bg-[#1e2536] text-white border border-[#2f3b55] disabled:opacity-40">Přidat</button>
            </form>
          </section>
        ))}
        <p className="text-[10px] text-gray-600">Kliknutím na tag ho přejmenuješ (u všech obchodů se změní taky).</p>
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
    stop_price: s(ex.stop_price),
    target_price: s(ex.target_price),
    outcome: s(ex.outcome),
    // čas ENTRY z grafu (datetime-local); bez něj zůstane předvyplněný aktuální čas
    ...(s(ex.traded_at) ? { traded_at: s(ex.traded_at) } : {}),
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
  const [engine, setEngineState] = useState<"claude" | "spark">(() => {
    try { const v = localStorage.getItem("tz_denik_engine"); return v === "spark" ? "spark" : "claude"; }
    catch { return "claude"; }
  });
  const setEngine = (k: "claude" | "spark") => {
    setEngineState(k);
    try { localStorage.setItem("tz_denik_engine", k); } catch { /* ignore */ }
  };
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
  const [tagData, setTagData] = useState<TagData>({ tags: [], strategies: [] });
  const [tagsOpen, setTagsOpen] = useState(false);
  const [filter, setFilter] = useState("");   // "" | "s:<id>" strategie | "t:<id>" tag
  const [day, setDay] = useState<string | null>(null);   // vybraný den v kalendáři (YYYY-MM-DD)

  // Bez setLoading(true) → refetch (po add/edit/delete/import) aktualizuje data
  // v místě, neblikne skeletonem přes celou stránku. Skeleton jen při 1. načtení
  // (loading init = true). Chyba refreshe nepřepisuje už zobrazená data.
  const reload = useCallback(async () => {
    try {
      const [list, st, tg] = await Promise.all([jFetch(""), jFetch("/stats"), jFetch("/tags")]);
      setEntries((list as { entries: Entry[] }).entries);
      // starší backend (při nasazování) nová pole nemá → prázdné výchozí hodnoty
      setStats({ by_strategy: [], by_tag: [], by_timeframe: [], by_combo: [], by_mistake: [], losses: { total: 0, explained: 0 }, ...(st as Partial<Stats>) } as Stats);
      setTagData(tg as TagData);
      setError(null);
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
    const prev = entries;
    setEntries((cur) => cur.filter((x) => x.id !== e.id)); // optimisticky — řádek zmizí hned
    try {
      await jFetch(`/${e.id}`, { method: "DELETE" });
      reload(); // tiše dosynchronizuj statistiky (bez blikání)
    } catch (err) {
      setEntries(prev); // rollback při chybě
      alert(err instanceof Error ? err.message : "Smazání selhalo");
    }
  };

  const tagById = useMemo(() => new Map(tagData.tags.map((x) => [x.id, x])), [tagData]);
  const stratById = useMemo(() => new Map(tagData.strategies.map((x) => [x.id, x])), [tagData]);
  const shown = useMemo(() => {
    const id = Number(filter.slice(2));
    return entries.filter((e) =>
      (!day || dayKey(e.traded_at) === day) &&
      (!filter || (filter.startsWith("s:") ? e.strategy_id === id : e.tag_ids.includes(id) || e.mistake_ids.includes(id))));
  }, [entries, filter, day]);

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
            {user.is_admin ? (
              <button onClick={() => setAnalyzeOpen(true)}
                className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium bg-blue-600/90 text-white border border-blue-500 hover:bg-blue-500 transition-colors">
                <Sparkles size={15} /> Z TradingView (AI)
              </button>
            ) : (
              // AI extrakce z grafu je zatím jen pro adminy (backend vrací 403) — ostatním coming soon
              <button type="button" disabled aria-disabled="true"
                title="AI čtení grafu z TradingView připravujeme"
                className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium bg-[#151823] text-gray-500 border border-[#2a2d3a] cursor-not-allowed">
                <Sparkles size={15} /> Z TradingView (AI)
                <span className="ml-1 rounded bg-blue-950/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-300">Coming soon</span>
              </button>
            )}
            <button onClick={() => setTagsOpen(true)}
              className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium bg-[#151823] text-gray-300 border border-[#2a2d3a] hover:text-white transition-colors">
              <Tags size={15} /> Tagy a strategie
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

          {t.trades > 0 && (stats!.by_strategy.length > 0 || stats!.by_tag.length > 0 || stats!.losses.total > 0) && (
            <div className="space-y-3">
              <div>
                <h2 className="text-base font-semibold text-white">Za jakých podmínek se ti daří</h2>
                <p className="text-xs text-gray-500">Obchod s více tagy se počítá do každého z nich. Kombinace = setup tagy + timeframe, ukazujeme ty s aspoň 2 obchody, seřazené podle Ø R. Na malém vzorku berte výsledky orientačně.</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                <BucketTable title="Podle strategie" rows={stats!.by_strategy} />
                <BucketTable title="Podle tagu" rows={stats!.by_tag} />
                <BucketTable title="Podle timeframe" rows={stats!.by_timeframe} />
                <BucketTable title="Nejlepší kombinace podmínek" rows={stats!.by_combo} />
                <MistakeTable rows={stats!.by_mistake} losses={stats!.losses} />
              </div>
            </div>
          )}

          {entries.length > 0 && <JournalCalendar entries={entries} selected={day} onSelect={setDay} />}

          {/* seznam obchodů */}
          {entries.length > 0 && (tagData.strategies.length > 0 || tagData.tags.length > 0) && (
            <div className="flex flex-wrap items-center gap-2 -mb-4">
              <select value={filter} onChange={(e) => setFilter(e.target.value)}
                className="rounded-lg bg-[#151823] border border-[#2a2d3a] px-3 py-1.5 text-xs text-gray-200">
                <option value="">Všechny obchody</option>
                {tagData.strategies.length > 0 && (
                  <optgroup label="Strategie">{tagData.strategies.map((x) => <option key={x.id} value={`s:${x.id}`}>{x.name}</option>)}</optgroup>
                )}
                {(["setup", "timeframe", "mistake"] as const).map((k) => (
                  <optgroup key={k} label={KIND_LABEL[k]}>
                    {tagData.tags.filter((x) => x.kind === k).map((x) => <option key={x.id} value={`t:${x.id}`}>{x.name}</option>)}
                  </optgroup>
                ))}
              </select>
              {day && (
                <button onClick={() => setDay(null)} className="flex items-center gap-1 rounded-lg border border-blue-800 bg-blue-950/40 px-2.5 py-1 text-xs text-blue-300">
                  {new Date(`${day}T12:00:00`).toLocaleDateString("cs", { day: "numeric", month: "numeric", year: "numeric" })} <X size={12} />
                </button>
              )}
              {(filter || day) && <span className="text-xs text-gray-500">{shown.length} z {entries.length}</span>}
            </div>
          )}
          {entries.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[#2a2d3a] bg-[#12141c] p-10 text-center">
              <TrendingUp size={28} className="mx-auto text-gray-600 mb-3" />
              <p className="text-gray-300 font-medium">Zatím žádné obchody</p>
              <p className="text-sm text-gray-500 mt-1">Přidej první záznam tlačítkem „Přidat obchod“ nahoře.</p>
            </div>
          ) : (
            <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[820px]">
                  <thead>
                    <tr className="text-gray-500 text-[10px] uppercase bg-[#181b26]">
                      <th className="text-left px-3 py-2.5">Datum</th>
                      <th className="text-left px-3 py-2.5">Instrument</th>
                      <th className="text-left px-3 py-2.5">Směr</th>
                      <th className="text-right px-3 py-2.5">SL / TP</th>
                      <th className="text-right px-3 py-2.5">Výsledek</th>
                      <th className="text-left px-3 py-2.5">Setup</th>
                      <th className="text-left px-3 py-2.5">Session</th>
                      <th className="text-left px-3 py-2.5">Pozn.</th>
                      <th className="px-3 py-2.5"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((e) => {
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
                          <td className="px-3 py-2.5 text-right text-xs text-gray-400 whitespace-nowrap">
                            {e.stop_price != null || e.target_price != null
                              ? <><span className="text-red-300">{e.stop_price ?? "—"}</span> / <span className="text-green-300">{e.target_price ?? "—"}</span></>
                              : "—"}
                          </td>
                          <td className="px-3 py-2.5 text-right font-semibold whitespace-nowrap" style={{ color: rColor(oc) }}>
                            {e.outcome && (
                              <span className={`mr-1.5 text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                                e.outcome === "win" ? "bg-green-950/60 text-green-300" : e.outcome === "loss" ? "bg-red-950/60 text-red-300" : "bg-gray-800 text-gray-300"}`}>
                                {e.outcome === "win" ? "WIN" : e.outcome === "loss" ? "LOSS" : "BE"}
                              </span>
                            )}
                            {e.r_result != null ? `${e.r_result > 0 ? "+" : ""}${e.r_result}R` : e.pnl != null ? `${e.pnl > 0 ? "+" : ""}${e.pnl}` : e.outcome ? "" : "—"}
                          </td>
                          <td className="px-3 py-2.5 text-gray-300 max-w-[220px]">
                            {e.strategy_id && stratById.get(e.strategy_id) && (
                              <div className="text-xs font-medium text-gray-100 truncate">{stratById.get(e.strategy_id)!.name}</div>
                            )}
                            <div className="flex flex-wrap gap-1 mt-0.5">
                              {e.tag_ids.map((id) => tagById.get(id)).filter(Boolean).map((tg) => (
                                <span key={tg!.id} className="rounded bg-blue-950/50 px-1.5 py-0.5 text-[10px] text-blue-300">{tg!.name}</span>
                              ))}
                              {e.mistake_ids.map((id) => tagById.get(id)).filter(Boolean).map((tg) => (
                                <span key={tg!.id} className="rounded bg-orange-950/50 px-1.5 py-0.5 text-[10px] text-orange-300" title="Chyba">{tg!.name}</span>
                              ))}
                            </div>
                            {!e.strategy_id && !e.tag_ids.length && !e.mistake_ids.length && <span className="text-xs">{e.setup || "—"}</span>}
                          </td>
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
      {formOpen && <EntryForm initial={editing} draft={draft} meta={lastMeta} tagData={tagData} onManageTags={() => setTagsOpen(true)} onClose={() => { setFormOpen(false); setEditing(null); setDraft(null); setLastMeta(null); }} onSaved={onSaved} />}
      {tagsOpen && <TagsModal data={tagData} onClose={() => setTagsOpen(false)} onChanged={reload} />}
    </div>
  );
}
