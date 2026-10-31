"use client";

import { useCallback, useEffect, useState } from "react";
import { Bell, BellRing, ChevronDown, ExternalLink, FileText, Loader2, Newspaper, X } from "lucide-react";
import { authHeaders } from "@/lib/auth";

export interface EarningsReport {
  id: number; ticker: string; name: string | null; accepted_at: string; source_url: string | null;
  fiscal_period: string | null; revenue: number | null; revenue_yoy_pct: number | null;
  eps_actual: number | null; eps_estimate: number | null; eps_surprise_pct: number | null; n_estimates: number | null;
  verdict: "positive" | "negative" | "mixed" | "neutral" | null;
  headline_cs: string | null; summary_cs: string | null; guidance_cs: string | null;
  price_before: number | null; price_now: number | null; reaction_pct: number | null; reaction_at: string | null;
  reaction_cs: string | null; related_news: { title: string; url: string | null; source: string; published_at: string | null }[];
}

const VERDICT: Record<string, { label: string; color: string }> = {
  positive: { label: "Pozitivní", color: "#4ade80" },
  negative: { label: "Negativní", color: "#f87171" },
  mixed: { label: "Smíšené", color: "#eab308" },
  neutral: { label: "Neutrální", color: "#9ca3af" },
};
const pct = (v: number | null, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toLocaleString("cs-CZ", { maximumFractionDigits: d })} %`);
const num = (v: number | null, d = 2) => (v == null ? "—" : v.toLocaleString("cs-CZ", { minimumFractionDigits: d, maximumFractionDigits: d }));
const bn = (v: number | null) => (v == null ? "—" : v >= 1e9 ? `${(v / 1e9).toLocaleString("cs-CZ", { maximumFractionDigits: 1 })} mld USD` : `${(v / 1e6).toLocaleString("cs-CZ", { maximumFractionDigits: 0 })} mil USD`);
const when = (iso: string) => new Date(iso).toLocaleString("cs-CZ", { day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });
const sign = (v: number | null) => (v == null ? "#9ca3af" : v > 0 ? "#4ade80" : v < 0 ? "#f87171" : "#9ca3af");

function Bullets({ text }: { text: string }) {
  const lines = text.split("\n").map((l) => l.replace(/^\s*[-•]\s*/, "").trim()).filter(Boolean);
  return (
    <ul className="list-disc space-y-1 pl-4 text-[12.5px] text-gray-300">
      {lines.map((l, i) => <li key={i}>{l}</li>)}
    </ul>
  );
}

export function EarningsReportCard({ r, open: initialOpen = false, onTicker }: {
  r: EarningsReport; open?: boolean; onTicker?: (t: string) => void;
}) {
  const [open, setOpen] = useState(initialOpen);
  const v = r.verdict ? VERDICT[r.verdict] : null;
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-3">
      <button onClick={() => setOpen((o) => !o)} className="w-full text-left">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold text-white" onClick={(e) => { if (onTicker) { e.stopPropagation(); onTicker(r.ticker); } }}
            title={onTicker ? "Otevřít detail firmy" : undefined}>{r.ticker}</span>
          {r.name && <span className="text-xs text-gray-400 truncate max-w-[180px]">{r.name}</span>}
          {r.fiscal_period && <span className="text-[11px] text-gray-500">{r.fiscal_period}</span>}
          {v && <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: v.color + "22", color: v.color }}>{v.label}</span>}
          {r.reaction_pct != null && (
            <span className="text-[11px] font-semibold" style={{ color: sign(r.reaction_pct) }} title="Pohyb akcie od zveřejnění výsledků">
              akcie {pct(r.reaction_pct)}
            </span>
          )}
          <span className="ml-auto flex items-center gap-1 text-[10px] text-gray-500">
            {when(r.accepted_at)} <ChevronDown size={13} className={open ? "rotate-180" : ""} />
          </span>
        </div>
        {r.headline_cs && <p className="mt-1 text-[13px] text-gray-200">{r.headline_cs}</p>}
        {!r.headline_cs && <p className="mt-1 text-[12px] text-gray-500">Výsledky zveřejněny — vysvětlení se připravuje.</p>}
      </button>

      {open && (
        <div className="mt-3 space-y-3 border-t border-[#232735] pt-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div className="rounded-lg bg-[#0f1117] px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider text-gray-500">Tržby</div>
              <div className="text-sm font-semibold text-white">{bn(r.revenue)}</div>
              {r.revenue_yoy_pct != null && <div className="text-[11px]" style={{ color: sign(r.revenue_yoy_pct) }}>{pct(r.revenue_yoy_pct)} meziročně</div>}
            </div>
            <div className="rounded-lg bg-[#0f1117] px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider text-gray-500">Zisk na akcii (EPS)</div>
              <div className="text-sm font-semibold text-white">{num(r.eps_actual)} USD</div>
              {r.eps_estimate != null && (
                <div className="text-[11px] text-gray-400">
                  odhad {num(r.eps_estimate)}{r.eps_surprise_pct != null && <> · <span style={{ color: sign(r.eps_surprise_pct) }}>{pct(r.eps_surprise_pct)}</span></>}
                </div>
              )}
            </div>
            <div className="rounded-lg bg-[#0f1117] px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider text-gray-500">Reakce akcie</div>
              <div className="text-sm font-semibold" style={{ color: sign(r.reaction_pct) }}>{pct(r.reaction_pct)}</div>
              {r.price_before != null && r.price_now != null && (
                <div className="text-[11px] text-gray-400">{num(r.price_before)} → {num(r.price_now)}{r.reaction_at ? ` · ${when(r.reaction_at)}` : ""}</div>
              )}
            </div>
          </div>

          {r.summary_cs && (
            <div>
              <div className="mb-1 text-[11px] font-semibold text-gray-200">Co to znamená pro firmu</div>
              <Bullets text={r.summary_cs} />
            </div>
          )}
          {r.guidance_cs && (
            <div className="text-[12.5px] text-gray-300"><span className="font-semibold text-gray-200">Výhled vedení:</span> {r.guidance_cs}</div>
          )}
          {r.reaction_cs && (
            <div className="rounded-lg border border-blue-900/50 bg-blue-950/20 px-3 py-2">
              <div className="mb-1 text-[11px] font-semibold text-blue-300">Proč trh reaguje takto</div>
              <Bullets text={r.reaction_cs} />
            </div>
          )}
          {r.related_news.length > 0 && (
            <div>
              <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold text-gray-200"><Newspaper size={12} /> Zprávy kolem výsledků</div>
              <ul className="space-y-0.5">
                {r.related_news.map((n, i) => (
                  <li key={i} className="text-[12px] text-gray-400">
                    {n.url ? <a href={n.url} target="_blank" rel="noopener noreferrer" className="hover:text-blue-300">{n.title}</a> : n.title}
                    <span className="text-gray-600"> · {n.source}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3 text-[10px] text-gray-500">
            {r.source_url && (
              <a href={r.source_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-blue-400 hover:text-blue-300">
                <FileText size={11} /> Tisková zpráva (SEC 8-K) <ExternalLink size={10} />
              </a>
            )}
            <span>Vysvětlení napsala AI z tiskové zprávy a konsenzu analytiků (Nasdaq). Není to investiční doporučení.</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function useReports(url: string) {
  const [reports, setReports] = useState<EarningsReport[] | null>(null);
  const load = useCallback(() => {
    fetch(url, { cache: "no-store", headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setReports(d?.reports ?? []))
      .catch(() => setReports([]));
  }, [url]);
  useEffect(() => {
    load();
    const id = setInterval(() => { if (document.visibilityState === "visible") load(); }, 120_000);
    return () => clearInterval(id);
  }, [load]);
  return reports;
}

// Žlutý vykřičník v radaru: čerstvé výsledky, které mění obrázek firmy (verdikt není neutrální
// nebo akcie výrazně reagovala). Skóre valuace je z dat před výsledky → stojí za to je prověřit.
export const ALERT_DAYS = 7;
const ALERT_MOVE_PCT = 3;

export function earningsAlerts(reports: EarningsReport[] | null): Record<string, EarningsReport> {
  const out: Record<string, EarningsReport> = {};
  const since = Date.now() - ALERT_DAYS * 86_400_000;
  for (const r of reports ?? []) {
    if (new Date(r.accepted_at).getTime() < since || out[r.ticker]) continue;   // feed je od nejnovějších
    const moved = r.reaction_pct != null && Math.abs(r.reaction_pct) >= ALERT_MOVE_PCT;
    if (moved || (r.verdict && r.verdict !== "neutral")) out[r.ticker] = r;
  }
  return out;
}

export function alertTitle(r: EarningsReport): string {
  const v = r.verdict ? VERDICT[r.verdict].label.toLowerCase() : "bez hodnocení";
  return `Nové výsledky ${when(r.accepted_at)} (${v}${r.reaction_pct != null ? `, akcie ${pct(r.reaction_pct)}` : ""})`
    + (r.headline_cs ? `: ${r.headline_cs}` : "") + " — skóre valuace ještě nemusí nové výsledky zohledňovat.";
}

/** Sekce v radaru: nejnovější výsledky hospodaření firem (data načítá stránka, obnova každé 2 min). */
export function EarningsFeed({ reports, onTicker }: { reports: EarningsReport[] | null; onTicker: (t: string) => void }) {
  const [all, setAll] = useState(false);
  if (!reports) return null;
  const shown = all ? reports : reports.slice(0, 4);
  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold text-white"><FileText size={15} className="text-blue-400" /> Výsledky hospodaření firem</h2>
        <span className="text-[11px] text-gray-500">hlídáme SEC — vysvětlení obvykle do pár minut po zveřejnění</span>
      </div>
      <EarningsAlertSettings />
      {reports.length === 0 ? (
        <p className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-3 text-[12px] text-gray-500">Zatím žádné zveřejněné výsledky firem z radaru.</p>
      ) : (
        <>
          {shown.map((r, i) => <EarningsReportCard key={r.id} r={r} open={i === 0} onTicker={onTicker} />)}
          {reports.length > 4 && (
            <button onClick={() => setAll((a) => !a)} className="text-[12px] text-blue-400 hover:text-blue-300">
              {all ? "Zobrazit méně" : `Zobrazit všechny (${reports.length})`}
            </button>
          )}
        </>
      )}
    </section>
  );
}

interface AlertSub { enabled: boolean; scope: "all" | "portfolio" | "custom"; tickers: string[]; only_critical: boolean; email: string | null }

const SCOPE_OPTS: { v: AlertSub["scope"]; label: string }[] = [
  { v: "all", label: "Všechny firmy v radaru" },
  { v: "portfolio", label: "Jen firmy v mém portfoliu" },
  { v: "custom", label: "Vybrané firmy" },
];

/** E-mailová upozornění na výsledky hospodaření (odběr per uživatel). */
function EarningsAlertSettings() {
  const [sub, setSub] = useState<AlertSub | null>(null);
  const [draft, setDraft] = useState<AlertSub | null>(null);
  const [tickerInput, setTickerInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    fetch("/api/valuation/earnings/alerts", { cache: "no-store", headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null)).then((d) => d && setSub(d)).catch(() => {});
  }, []);
  if (!sub) return null;

  async function call(method: "PUT" | "POST", url: string, body?: unknown) {
    setBusy(true); setMsg(null);
    try {
      const res = await fetch(url, {
        method, headers: { "Content-Type": "application/json", ...authHeaders() },
        body: body ? JSON.stringify(body) : undefined,
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) { setMsg({ ok: false, text: d.detail || "Nepodařilo se." }); return null; }
      return d;
    } catch { setMsg({ ok: false, text: "Chyba připojení." }); return null; } finally { setBusy(false); }
  }

  function addTickers() {
    if (!draft) return;
    const add = tickerInput.toUpperCase().split(/[\s,;]+/).map((t) => t.replace(/[^A-Z0-9.-]/g, "")).filter(Boolean);
    setDraft({ ...draft, tickers: [...new Set([...draft.tickers, ...add])].slice(0, 50) });
    setTickerInput("");
  }

  async function save(next: AlertSub) {
    const d = await call("PUT", "/api/valuation/earnings/alerts", next);
    if (d) { setSub(d); setDraft(null); setMsg({ ok: true, text: d.enabled ? `Uloženo — upozornění půjdou na ${d.email}.` : "Upozornění vypnuta." }); }
  }

  const scopeText = sub.scope === "portfolio" ? "firmy v portfoliu" : sub.scope === "custom" ? sub.tickers.join(", ") : "všechny firmy v radaru";
  if (!draft) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-[#2a2d3a] bg-[#151823] px-3 py-2 text-[12px]">
        {sub.enabled ? <BellRing size={14} className="text-yellow-400" /> : <Bell size={14} className="text-gray-500" />}
        <span className="text-gray-300">
          {sub.enabled
            ? <>E-mail na <b className="text-white">{sub.email}</b> · {sub.only_critical ? "kritické výsledky" : "všechny výsledky"} · {scopeText}</>
            : "Chceš dostat e-mail, jakmile firma zveřejní důležité výsledky?"}
        </span>
        <button onClick={() => setDraft({ ...sub, enabled: true })}
          className="ml-auto rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-3 py-1 text-[12px] font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)]">
          {sub.enabled ? "Upravit" : "Zapnout upozornění"}
        </button>
        {sub.enabled && (
          <button disabled={busy} onClick={() => save({ ...sub, enabled: false })} className="text-[12px] text-gray-500 hover:text-gray-300">Vypnout</button>
        )}
        {msg && <span className={`w-full text-[11px] ${msg.ok ? "text-[#8fffab]" : "text-red-400"}`}>{msg.text}</span>}
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-xl border border-[#2f3b55] bg-[#151823] p-3 text-[12.5px]">
      <div className="flex items-center gap-2">
        <BellRing size={14} className="text-yellow-400" />
        <span className="font-semibold text-white">Upozornění na výsledky hospodaření e-mailem</span>
        <button onClick={() => { setDraft(null); setMsg(null); }} className="ml-auto text-gray-500 hover:text-gray-300" aria-label="Zavřít"><X size={14} /></button>
      </div>
      {!sub.email && <p className="text-red-400">Účet nemá e-mail — upozornění nejde posílat.</p>}
      <div className="space-y-1">
        <div className="text-[11px] uppercase tracking-wider text-gray-500">Které firmy</div>
        {SCOPE_OPTS.map((o) => (
          <label key={o.v} className="flex cursor-pointer items-center gap-2 text-gray-300">
            <input type="radio" name="alert-scope" checked={draft.scope === o.v} onChange={() => setDraft({ ...draft, scope: o.v })} /> {o.label}
          </label>
        ))}
        {draft.scope === "custom" && (
          <div className="ml-6 space-y-1.5">
            <div className="flex flex-wrap gap-1">
              {draft.tickers.map((t) => (
                <span key={t} className="flex items-center gap-1 rounded bg-[#1e2536] px-1.5 py-0.5 text-[11px] text-white">
                  {t}<button onClick={() => setDraft({ ...draft, tickers: draft.tickers.filter((x) => x !== t) })} aria-label={`Odebrat ${t}`}><X size={10} /></button>
                </span>
              ))}
            </div>
            <div className="flex gap-1.5">
              <input value={tickerInput} onChange={(e) => setTickerInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTickers(); } }}
                placeholder="Tickery, např. GOOGL, MSFT"
                className="min-w-0 flex-1 rounded-lg border border-[#2a2d3a] bg-[#0f1117] px-2 py-1 text-[12px] text-gray-200 placeholder-gray-600 focus:border-[#60ff82] focus:outline-none" />
              <button onClick={addTickers} className="rounded-lg border border-[#2a2d3a] px-2 text-[12px] text-gray-300 hover:text-white">Přidat</button>
            </div>
          </div>
        )}
      </div>
      <div className="space-y-1">
        <div className="text-[11px] uppercase tracking-wider text-gray-500">Které výsledky</div>
        <label className="flex cursor-pointer items-start gap-2 text-gray-300">
          <input type="radio" name="alert-crit" className="mt-0.5" checked={draft.only_critical} onChange={() => setDraft({ ...draft, only_critical: true })} />
          <span>Jen kritické <span className="text-gray-500">— jako žlutý vykřičník: verdikt pozitivní / negativní / smíšený, nebo akcie pohnula o 3 % a víc</span></span>
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-gray-300">
          <input type="radio" name="alert-crit" checked={!draft.only_critical} onChange={() => setDraft({ ...draft, only_critical: false })} /> Všechny zveřejněné výsledky
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button disabled={busy || !sub.email || (draft.scope === "custom" && draft.tickers.length === 0)} onClick={() => save({ ...draft, enabled: true })}
          className="flex items-center gap-1.5 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-3 py-1.5 text-[12px] font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)] disabled:opacity-50">
          {busy && <Loader2 size={12} className="animate-spin" />} Uložit a zapnout
        </button>
        {sub.enabled && (
          <button disabled={busy} onClick={async () => {
            const d = await call("POST", "/api/valuation/earnings/alerts/test");
            if (d) setMsg({ ok: true, text: `Zkušební e-mail (${d.ticker}) odeslán na ${d.email}.` });
          }} className="rounded-lg border border-[#2a2d3a] px-3 py-1.5 text-[12px] text-gray-300 hover:text-white disabled:opacity-50">
            Poslat zkušební e-mail
          </button>
        )}
        <span className="text-[11px] text-gray-500">na {sub.email ?? "—"} · odhlásit jde i odkazem v e-mailu</span>
      </div>
      {msg && <p className={`text-[11px] ${msg.ok ? "text-[#8fffab]" : "text-red-400"}`}>{msg.text}</p>}
    </div>
  );
}

/** Výsledky hospodaření jedné firmy (v detailu firmy). */
export function TickerEarnings({ ticker }: { ticker: string }) {
  const reports = useReports(`/api/valuation/${ticker}/earnings`);
  if (!reports || reports.length === 0) return null;
  return (
    <div className="mb-3 space-y-2">
      <h3 className="text-sm font-semibold text-white">Výsledky hospodaření</h3>
      {reports.map((r, i) => <EarningsReportCard key={r.id} r={r} open={i === 0} />)}
    </div>
  );
}
