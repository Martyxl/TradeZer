"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Lock, Search } from "lucide-react";
import { BubbleMap, type OverviewItem } from "@/components/valuation/BubbleMap";
import { companyHref, dateCs, useRadar } from "./data";
import { Card } from "./ui";
import type { Bucket, Pillar, Radar, RadarItem } from "./types";

// Barvy skupin — třídy, které světlý motiv přemapuje (globals.css).
const BUCKET: Record<Bucket, { label: string; cls: string }> = {
  cheap: { label: "Levná", cls: "bg-emerald-950/60 text-emerald-300 ring-1 ring-inset ring-emerald-500/40" },
  fair: { label: "Férová cena", cls: "bg-blue-950/50 text-blue-300" },
  expensive: { label: "Drahá", cls: "bg-red-950/50 text-red-300 ring-1 ring-inset ring-red-500/40" },
  unknown: { label: "Bez hodnocení", cls: "bg-raised text-gray-400" },
};

export function BucketPill({ bucket, label, big = false }: { bucket: Bucket; label?: string | null; big?: boolean }) {
  const b = BUCKET[bucket];
  return (
    <span className={`inline-flex items-center justify-center whitespace-nowrap rounded-full font-semibold ${b.cls} ${big ? "px-3 py-1 text-[13px]" : "w-full px-2 py-0.5 text-[11.5px]"}`}>
      {label || b.label}
    </span>
  );
}

const LEVEL: Record<Pillar["level"], { word: string; color: string }> = {
  good: { word: "Dobré", color: "#4ade80" }, ok: { word: "Průměr", color: "#f59e0b" },
  weak: { word: "Slabé", color: "#ef4444" }, none: { word: "Bez dat", color: "#6b7280" },
};

export function PillarCard({ p }: { p: Pillar }) {
  const l = LEVEL[p.level];
  return (
    <div className="rounded-xl border border-line bg-sunken p-3.5">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-[11.5px] text-gray-500">{p.label}</div>
          <div className="text-[14px] font-semibold text-white">{p.question}</div>
        </div>
        <span className="flex shrink-0 items-center gap-1.5 text-[12.5px] font-semibold" style={{ color: l.color }}>
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: l.color }} />{l.word}
        </span>
      </div>
      {p.score != null && (
        <div className="mt-2 h-1.5 rounded-full bg-raised" title={`skóre ${Math.round(p.score)} / 100`}>
          <div className="h-full rounded-full" style={{ width: `${Math.max(3, p.score)}%`, background: l.color }} />
        </div>
      )}
      <p className="mt-2 text-[13px] leading-relaxed text-gray-300">{p.text}</p>
    </div>
  );
}

/** Radar je ve stejném tarifu jako plný Valuation Radar. */
export function PlanNeeded() {
  return (
    <Card className="text-center">
      <Lock size={20} className="mx-auto text-gray-500" />
      <p className="mt-2 text-sm text-gray-300">Radar firem je součástí tarifu <b className="text-white">Trader</b> — stejně jako Valuation Radar v režimu Pokročilý.</p>
      <Link href="/predplatne" className="mt-3 inline-block rounded-full bg-white px-4 py-2 text-sm font-semibold text-on-ink hover:bg-white/85">Zobrazit tarify</Link>
    </Card>
  );
}

/** Mapa zón (stejná jako ve Valuation Radaru) se srozumitelnými popisky. Klik na bublinu → karta firmy. */
export function ZoneMap({ radar, focus = null }: { radar: Radar; focus?: string | null }) {
  const router = useRouter();
  const items = useMemo<OverviewItem[]>(() => radar.items.map((i) => ({
    ticker: i.ticker, name: i.name, group_key: null, pctile_pe_fwd: i.pctile_pe_fwd, eps_growth_ntm: i.eps_growth_ntm,
    market_cap: i.market_cap, valuation_score: null, composite_score: i.score, valuation_verdict: i.verdict,
    horizon_verdict: null, bubble_flag: i.bubble_flag, confidence: i.confidence,
    zone: (i.zone as OverviewItem["zone"]) ?? null, zone_reliable: i.reliable,
  })), [radar]);
  const marked = useMemo(() => new Set(radar.items.filter((i) => i.held).map((i) => i.ticker)), [radar]);
  return (
    <BubbleMap items={items} zones={radar.zones} focus={focus} marked={marked} simple
      onSelect={(t) => router.push(companyHref(t))} />
  );
}

/** Jak číst mapu — jednou větou pro začátečníka. */
export function ZoneMapLegend({ held = true }: { held?: boolean }) {
  return (
    <div className="mt-2 space-y-1 text-[12px] leading-relaxed text-gray-400">
      <p>
        <b className="text-gray-300">Jak číst mapu:</b> vlevo jsou firmy levnější, než bývají, nahoře ty, kterým rychle roste zisk.
        <span className="text-emerald-300"> Zelená plocha vlevo nahoře</span> = levné vzhledem k růstu — tam hledej nákupy.
        <span className="text-red-300"> Červená vpravo dole</span> = drahé vzhledem k růstu — tam spíš nekupuj.
      </p>
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-gray-500">
        <span>velikost bubliny = velikost firmy</span>
        {held && <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-[#60b4ff]" /> firmy, které máš</span>}
        <span><span className="text-red-400">⚠</span> = možná bublina</span>
        <span>klikni na bublinu pro detail</span>
      </p>
    </div>
  );
}

type Tab = Bucket | "mine" | "all";
const TABS: [Tab, string][] = [["cheap", "Levné"], ["fair", "Férová cena"], ["expensive", "Drahé"], ["mine", "Moje firmy"], ["all", "Vše"]];
const PAGE = 40;

/** Radar firem na Přehledu: mapa zón vlevo (drží se při posouvání), seznam firem vpravo. */
export function RadarPanel() {
  const { data, error, status } = useRadar();
  const [tab, setTab] = useState<Tab>("cheap");
  const [q, setQ] = useState("");
  const [shown, setShown] = useState(PAGE);
  const ready = data != null || status != null;

  // Odkaz /investor#radar: sekce se vykreslí až po načtení dat, takže prohlížeč na ni sám neodskočí.
  useEffect(() => {
    if (ready && window.location.hash === "#radar") {
      const t = setTimeout(() => document.getElementById("radar")?.scrollIntoView({ block: "start" }), 400);
      return () => clearTimeout(t);
    }
  }, [ready]);

  const counts = useMemo(() => {
    const c: Record<Tab, number> = { cheap: 0, fair: 0, expensive: 0, unknown: 0, mine: 0, all: 0 };
    for (const i of data?.items ?? []) { c[i.bucket]++; c.all++; if (i.held) c.mine++; }
    return c;
  }, [data]);

  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data?.items ?? []).filter((i: RadarItem) => {
      if (needle) return i.ticker.toLowerCase().includes(needle) || (i.name ?? "").toLowerCase().includes(needle);
      return tab === "all" ? true : tab === "mine" ? i.held : i.bucket === tab;
    });
  }, [data, tab, q]);

  const head = (
    <div>
      <h2 className="text-lg font-bold text-white">Radar firem</h2>
      <p className="text-[12.5px] text-gray-500">Jak drahé jsou velké firmy vůči tomu, kolik vydělávají a jak rychle rostou. Klikni na firmu a uvidíš proč.</p>
    </div>
  );
  const wrap = (body: React.ReactNode) => <section id="radar" className="scroll-mt-5 space-y-3">{head}{body}</section>;

  if (status === 403) return wrap(<PlanNeeded />);
  if (error) return wrap(<Card><p className="text-sm text-amber-300">Radar se nepodařilo načíst. Zkus to za chvíli znovu.</p></Card>);
  if (!data) return wrap(<div className="h-96 animate-pulse rounded-2xl bg-panel" />);

  return wrap(
    <>
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card className="xl:sticky xl:top-5">
          <h3 className="mb-2 text-[15px] font-bold text-white">Mapa: kde je která firma</h3>
          <ZoneMap radar={data} />
          <ZoneMapLegend held={counts.mine > 0} />
        </Card>

        <Card className="p-0 md:p-0">
          <div className="flex flex-col gap-3 border-b border-line px-4 py-3 md:px-5">
            <label className="relative block">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input value={q} onChange={(e) => { setQ(e.target.value); setShown(PAGE); }} placeholder="Hledat firmu (např. Apple, MSFT)"
                className="inv-input w-full pl-8" aria-label="Hledat firmu" />
            </label>
            {!q && (
              <div className="flex flex-wrap gap-1.5" role="tablist">
                {TABS.map(([k, label]) => (
                  <button key={k} role="tab" aria-selected={tab === k} onClick={() => { setTab(k); setShown(PAGE); }}
                    className={`rounded-full border px-3 py-1 text-[12.5px] transition-colors ${tab === k ? "border-[rgba(96,255,130,0.55)] bg-neon-tint text-white" : "border-line text-gray-300 hover:text-white"}`}>
                    {label} <span className="text-gray-500">{counts[k]}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          {list.length === 0 ? (
            <p className="px-4 py-6 text-sm text-gray-500 md:px-5">
              {q ? "Žádná sledovaná firma neodpovídá hledání." : tab === "mine" ? "Žádnou z tvých akcií Radar nesleduje (fondy nehodnotí)." : "V této skupině teď nic není."}
            </p>
          ) : (
            <ul className="max-h-[640px] divide-y divide-line overflow-y-auto">
              {list.slice(0, shown).map((i) => (
                <li key={i.ticker}>
                  <Link href={companyHref(i.ticker)} className="flex items-center gap-3 px-4 py-3 hover:bg-raised/40 md:px-5">
                    <div className="w-[92px] shrink-0"><BucketPill bucket={i.bucket} label={i.verdict_label} /></div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-2">
                        <span className="font-semibold text-white">{i.ticker}</span>
                        <span className="truncate text-[12px] text-gray-500">{i.name}</span>
                        {i.held && <span className="shrink-0 rounded-full bg-emerald-950/60 px-2 py-px text-[11px] text-emerald-300">máš</span>}
                      </div>
                      {i.text && <p className="truncate text-[12.5px] text-gray-400">{i.text}{!i.reliable && " · data neúplná"}</p>}
                    </div>
                    <ChevronRight size={16} className="shrink-0 text-gray-600" />
                  </Link>
                </li>
              ))}
              {list.length > shown && (
                <li className="px-4 py-3 text-center md:px-5">
                  <button onClick={() => setShown((s) => s + PAGE)} className="text-[13px] font-semibold text-neon-soft hover:underline">
                    Zobrazit další ({list.length - shown})
                  </button>
                </li>
              )}
            </ul>
          )}
        </Card>
      </div>
      <p className="text-[11.5px] leading-relaxed text-gray-500">
        <b className="text-gray-400">Levná</b> = cena je nízko vůči ziskům a jejich růstu, <b className="text-gray-400">Drahá</b> = trh už
        započítal hodně dobrých zpráv. Hodnotí se jen jednotlivé firmy, ne fondy.
        {data.as_of && ` Data k ${dateCs(data.as_of)}.`} Všechna čísla najdeš v režimu Pokročilý (Valuation Radar). Nejde o investiční doporučení.
      </p>
    </>
  );
}
