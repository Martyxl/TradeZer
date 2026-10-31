"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ExternalLink, FileText, Newspaper } from "lucide-react";
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
