"use client";

import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";

export interface Regime {
  state: "calm" | "recovering" | "tension" | "panic" | null;
  label?: string;
  policy?: string;
  reasons?: string[];
  indicators?: Record<string, number | boolean | null>;
  geo?: {
    severity: number; summary?: string; n_headlines?: number;
    headlines?: { title: string; source: string; severity: number; why: string }[];
  } | null;
  as_of?: string;
}

const TONE: Record<string, { box: string; dot: string; text: string }> = {
  calm:       { box: "border-[rgba(96,255,130,0.25)] bg-[#0c1a11]", dot: "#60ff82", text: "text-[#8fffab]" },
  recovering: { box: "border-[rgba(96,180,255,0.3)] bg-[#0c1522]",  dot: "#60b4ff", text: "text-[#9fd0ff]" },
  tension:    { box: "border-[rgba(255,196,64,0.35)] bg-[#1c1608]", dot: "#ffc440", text: "text-[#ffd97a]" },
  panic:      { box: "border-[rgba(255,80,80,0.4)] bg-[#1c0c0c]",   dot: "#ff5050", text: "text-[#ff8f8f]" },
};

export function useRegime(): Regime | null {
  const [r, setR] = useState<Regime | null>(null);
  useEffect(() => {
    let alive = true;
    fetch("/api/regime", { cache: "no-store" })
      .then((x) => (x.ok ? x.json() : Promise.reject()))
      .then((j: Regime) => { if (alive && j.state) setR(j); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  return r;
}

const num = (v: unknown) => (typeof v === "number" ? v : null);
const pct = (v: unknown) => (num(v) == null ? "—" : `${num(v)! >= 0 ? "+" : ""}${num(v)!.toFixed(1)} %`);

function when(asOf?: string): string {
  if (!asOf) return "";
  const d = new Date(asOf);
  return isNaN(d.getTime()) ? "" : d.toLocaleString("cs-CZ", { day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Malý štítek stavu trhu (např. na stránce fondu). */
export function RegimeChip() {
  const r = useRegime();
  if (!r?.state) return null;
  const t = TONE[r.state];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] ${t.box}`} title={r.policy}>
      <span className="h-2 w-2 rounded-full" style={{ background: t.dot }} />
      <span className="text-gray-400">Režim trhu:</span>
      <b className={t.text}>{r.label}</b>
    </span>
  );
}

/** Karta „Režim trhu" na dashboardu — skryje se, když nejsou data. */
export function RegimeCard() {
  const r = useRegime();
  if (!r?.state) return null;
  const t = TONE[r.state];
  const i = r.indicators || {};
  const cells: [string, string][] = [
    ["VIX", num(i.vix) != null ? num(i.vix)!.toFixed(1) : "—"],
    ["S&P 500 (den / 5 dní)", `${pct(i.spx_chg_1d)} / ${pct(i.spx_chg_5d)}`],
    ["Ropa (5 dní)", pct(i.oil_chg_5d)],
    ["Zlato (5 dní)", pct(i.gold_chg_5d)],
    ["Výnos US10Y", num(i.us10y) != null ? `${num(i.us10y)!.toFixed(2)} %` : "—"],
  ];
  const geo = r.geo;
  return (
    <div className={`rounded-xl border px-4 py-3 ${t.box}`}>
      <div className="flex flex-wrap items-center gap-2">
        <ShieldAlert size={15} className={t.text} />
        <span className="text-[11px] uppercase tracking-wider text-gray-400">Režim trhu</span>
        <span className="flex items-center gap-1.5 rounded-md px-2 py-0.5 text-sm font-semibold" style={{ color: t.dot, background: "rgba(255,255,255,0.05)" }}>
          <span className="h-2 w-2 rounded-full" style={{ background: t.dot }} />{r.label}
        </span>
        {r.as_of && <span className="ml-auto text-[10px] text-gray-500">aktualizováno {when(r.as_of)}</span>}
      </div>
      {r.policy && <p className="mt-1.5 text-sm text-gray-200">{r.policy}</p>}
      {!!r.reasons?.length && (
        <ul className="mt-1 list-disc pl-5 text-xs text-gray-400">{r.reasons.map((x, k) => <li key={k}>{x}</li>)}</ul>
      )}
      <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {cells.map(([k, v]) => (
          <div key={k} className="rounded-lg bg-black/25 px-2.5 py-1.5">
            <div className="text-[10px] text-gray-500">{k}</div>
            <div className="text-sm font-medium text-gray-100">{v}</div>
          </div>
        ))}
      </div>
      {geo && (
        <div className="mt-2.5 text-xs text-gray-400">
          <span className="text-gray-500">Svět (AI hodnocení titulků, {geo.severity}/3):</span>{" "}
          {geo.summary || "bez shrnutí"}
          {!!geo.headlines?.length && (
            <ul className="mt-1 space-y-0.5 text-[11px] text-gray-500">
              {geo.headlines.slice(0, 3).map((h, k) => (
                <li key={k}>• {h.title} <span className="text-gray-600">({h.source})</span></li>
              ))}
            </ul>
          )}
        </div>
      )}
      <p className="mt-2 text-[10px] text-gray-600">
        Pravidlový ukazatel, ne investiční doporučení. Titulky hodnotí AI a samy o sobě nikdy nespustí paniku — potřebují potvrzení trhem.
      </p>
    </div>
  );
}
