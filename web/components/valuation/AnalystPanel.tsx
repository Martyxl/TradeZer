"use client";

import { useEffect, useState } from "react";
import { Building2, Users } from "lucide-react";
import { authHeaders } from "@/lib/auth";

interface Counts { strong_buy: number; buy: number; hold: number; sell: number; strong_sell: number }
interface Revision {
  period: string; date: string | null; eps: number | null; chg_7d: number | null; chg_30d: number | null;
  chg_90d: number | null; up_month: number | null; down_month: number | null;
}
interface Holder { name: string | null; pct: number | null; value: number | null; date: string | null }
interface Analysts {
  ticker: string; updated_at: string | null;
  price_target?: { low: number | null; median: number | null; average: number | null; high: number | null; current: number | null; upside_pct: number | null };
  recommendations?: { now: Counts | null; "3m_ago": Counts | null };
  revisions?: Revision[];
  growth?: Record<string, number | null>;
  actions?: { date: string; firm: string; rating_change: string | null; rating_current: string | null; rating_prior: string | null; price_target_current: number | null; price_target_prior: number | null }[];
  holders?: { institutions: Holder[]; funds: Holder[] };
}

const n2 = (v: number | null | undefined, d = 2) => (v == null ? "—" : v.toLocaleString("cs-CZ", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toLocaleString("cs-CZ", { maximumFractionDigits: d })} %`);
const col = (v: number | null | undefined) => (v == null || v === 0 ? "#9ca3af" : v > 0 ? "#4ade80" : "#f87171");
const PERIOD = { current_quarter: "tento kvartál", current_year: "letos", next_year: "příští rok" } as Record<string, string>;
const CHANGE = { Upgrade: "zvýšil", Downgrade: "snížil", Initiates: "začal pokrývat", Maintains: "potvrdil", Reiterates: "potvrdil" } as Record<string, string>;
const box = "rounded-xl border border-[#2a2d3a] bg-[#151823] p-3";
const head = "text-[10px] uppercase tracking-wider text-gray-500 mb-2";

function TargetBar({ t }: { t: NonNullable<Analysts["price_target"]> }) {
  const { low, high, current, average } = t;
  if (low == null || high == null || high <= low) return null;
  const pos = (v: number | null) => (v == null ? null : Math.min(100, Math.max(0, ((v - low) / (high - low)) * 100)));
  const c = pos(current), a = pos(average);
  return (
    <div className="mt-2">
      <div className="relative h-2 rounded-full bg-gradient-to-r from-[#7f1d1d] via-[#3f3f46] to-[#14532d]">
        {a != null && <span className="absolute -top-1 h-4 w-0.5 bg-white" style={{ left: `${a}%` }} title="průměrná cílová cena" />}
        {c != null && <span className="absolute -top-1.5 h-5 w-1.5 -translate-x-1/2 rounded bg-[#60a5fa]" style={{ left: `${c}%` }} title="aktuální cena" />}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-gray-500">
        <span>min {n2(low)}</span><span className="text-[#60a5fa]">cena {n2(current)}</span><span>max {n2(high)}</span>
      </div>
    </div>
  );
}

function RecBar({ c }: { c: Counts }) {
  const parts = [
    { k: "strong_buy", v: c.strong_buy, color: "#16a34a", label: "silně koupit" },
    { k: "buy", v: c.buy, color: "#4ade80", label: "koupit" },
    { k: "hold", v: c.hold, color: "#a1a1aa", label: "držet" },
    { k: "sell", v: c.sell, color: "#f87171", label: "prodat" },
    { k: "strong_sell", v: c.strong_sell, color: "#b91c1c", label: "silně prodat" },
  ];
  const total = parts.reduce((s, p) => s + (p.v || 0), 0);
  if (!total) return null;
  return (
    <>
      <div className="flex h-2.5 overflow-hidden rounded-full">
        {parts.map((p) => p.v ? <span key={p.k} style={{ width: `${(p.v / total) * 100}%`, background: p.color }} title={`${p.label}: ${p.v}`} /> : null)}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-2 text-[10px] text-gray-500">
        {parts.filter((p) => p.v).map((p) => <span key={p.k}><span style={{ color: p.color }}>■</span> {p.label} {p.v}</span>)}
      </div>
    </>
  );
}

const buyShare = (c: Counts | null | undefined) => {
  if (!c) return null;
  const t = c.strong_buy + c.buy + c.hold + c.sell + c.strong_sell;
  return t ? Math.round(((c.strong_buy + c.buy) / t) * 100) : null;
};

/** Detail firmy: co si o ní myslí analytici a kdo ji vlastní (Twelve Data, obnova 1× denně). */
export function AnalystPanel({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Analysts | null>(null);
  useEffect(() => {
    setD(null);
    fetch(`/api/valuation/${ticker}/analysts`, { cache: "no-store", headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null)).then(setD).catch(() => setD(null));
  }, [ticker]);
  if (!d) return null;
  const t = d.price_target, rec = d.recommendations;
  const share = buyShare(rec?.now), share3 = buyShare(rec?.["3m_ago"]);
  const g = d.growth ?? {};
  return (
    <div className="mb-3 space-y-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-white"><Users size={14} className="text-blue-400" /> Analytici</h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {t && (
          <div className={box}>
            <div className={head}>Cílová cena (12 měsíců)</div>
            <div className="text-sm text-white">
              průměr <b>{n2(t.average)} USD</b>{" "}
              <span className="font-semibold" style={{ color: col(t.upside_pct) }}>{pct(t.upside_pct)}</span>
              <span className="text-[11px] text-gray-500"> od aktuální ceny</span>
            </div>
            <TargetBar t={t} />
          </div>
        )}
        {rec?.now && (
          <div className={box}>
            <div className={head}>Doporučení</div>
            <div className="mb-1.5 text-sm text-white">
              {share != null && <><b>{share} %</b> analytiků doporučuje koupit</>}
              {share != null && share3 != null && share !== share3 && (
                <span className="text-[11px]" style={{ color: col(share - share3) }}> ({share > share3 ? "+" : ""}{share - share3} b. za 3 měsíce)</span>
              )}
            </div>
            <RecBar c={rec.now} />
          </div>
        )}
        {d.revisions && d.revisions.length > 0 && (
          <div className={box}>
            <div className={head}>Revize odhadů zisku (EPS)</div>
            <table className="w-full text-[11px] text-gray-300">
              <thead><tr className="text-gray-500"><th className="text-left font-normal" /><th className="text-right font-normal">odhad</th><th className="text-right font-normal">30 dní</th><th className="text-right font-normal">90 dní</th><th className="text-right font-normal">↑/↓ měsíc</th></tr></thead>
              <tbody>
                {d.revisions.map((r) => (
                  <tr key={r.period}>
                    <td className="py-0.5 text-gray-400">{PERIOD[r.period] ?? r.period}</td>
                    <td className="text-right">{n2(r.eps)}</td>
                    <td className="text-right" style={{ color: col(r.chg_30d) }}>{pct(r.chg_30d)}</td>
                    <td className="text-right" style={{ color: col(r.chg_90d) }}>{pct(r.chg_90d)}</td>
                    <td className="text-right"><span className="text-[#4ade80]">{r.up_month ?? 0}</span>/<span className="text-[#f87171]">{r.down_month ?? 0}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-[10px] text-gray-600">Změna konsenzu = kladná, když analytici čekají vyšší zisk (u ztrátových firem menší ztrátu). ↑/↓ = kolik analytiků za měsíc odhad zvýšilo/snížilo.</p>
          </div>
        )}
        {(g.current_year != null || g.next_year != null) && (
          <div className={box}>
            <div className={head}>Očekávaný růst zisku</div>
            {([["current_quarter", "tento kvartál (r/r)"], ["current_year", "letos"], ["next_year", "příští rok"], ["next_5_years_pa", "dalších 5 let (ročně)"]] as const).map(([k, label]) => (
              g[k] != null ? (
                <div key={k} className="flex justify-between py-0.5 text-[11px] text-gray-300">
                  <span className="text-gray-400">{label}</span><span style={{ color: col(g[k]) }}>{pct(g[k])}</span>
                </div>
              ) : null
            ))}
          </div>
        )}
      </div>
      {d.actions && d.actions.length > 0 && (
        <div className={box}>
          <div className={head}>Poslední akce analytiků</div>
          {d.actions.slice(0, 6).map((a, i) => {
            const pt = a.price_target_current, pp = a.price_target_prior;
            return (
              <div key={i} className="flex flex-wrap gap-x-2 py-0.5 text-[11px] text-gray-300">
                <span className="w-16 shrink-0 text-gray-500">{new Date(a.date).toLocaleDateString("cs-CZ", { day: "numeric", month: "numeric" })}</span>
                <span className="font-medium text-white">{a.firm}</span>
                <span style={{ color: a.rating_change === "Upgrade" ? "#4ade80" : a.rating_change === "Downgrade" ? "#f87171" : "#9ca3af" }}>
                  {CHANGE[a.rating_change ?? ""] ?? a.rating_change} {a.rating_current}{a.rating_prior && a.rating_prior !== a.rating_current ? ` (dřív ${a.rating_prior})` : ""}
                </span>
                {pt != null && (
                  <span className="text-gray-400">cíl {pp != null && pp !== pt ? <>{n2(pp, 0)} → </> : null}<b style={{ color: pp != null ? col(pt - pp) : "#e5e7eb" }}>{n2(pt, 0)}</b></span>
                )}
              </div>
            );
          })}
        </div>
      )}
      {d.holders && (d.holders.institutions.length > 0 || d.holders.funds.length > 0) && (
        <div className={box}>
          <div className={`${head} flex items-center gap-1`}><Building2 size={11} /> Největší vlastníci</div>
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            {([["Instituce", d.holders.institutions], ["Fondy", d.holders.funds]] as const).map(([label, rows]) => rows.length > 0 && (
              <div key={label}>
                <div className="mb-0.5 text-[10px] text-gray-500">{label}</div>
                {rows.slice(0, 5).map((h, i) => (
                  <div key={i} className="flex justify-between gap-2 py-0.5 text-[11px] text-gray-300">
                    <span className="truncate" title={h.name ?? ""}>{h.name}</span>
                    <span className="shrink-0 text-gray-400">{h.pct != null ? `${(h.pct * 100).toLocaleString("cs-CZ", { maximumFractionDigits: 1 })} %` : "—"}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
      <p className="text-[10px] text-gray-600">Data analytiků a vlastníků: Twelve Data{d.updated_at ? `, aktualizováno ${new Date(d.updated_at).toLocaleDateString("cs-CZ")}` : ""}. Názory analytiků nejsou investiční doporučení.</p>
    </div>
  );
}
