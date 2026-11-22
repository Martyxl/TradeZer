"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useRadar, dateCs, companyHref } from "@/components/investor/data";
import { Card, Disclaimer, LoginNeeded } from "@/components/investor/ui";
import { BucketPill, PlanNeeded, ZoneMap, ZoneMapLegend } from "@/components/investor/radar";
import type { Bucket, RadarItem } from "@/components/investor/types";

type Tab = Bucket | "mine" | "all";
const TABS: [Tab, string][] = [["cheap", "Levné"], ["fair", "Férová cena"], ["expensive", "Drahé"], ["mine", "Moje firmy"], ["all", "Vše"]];
const PAGE = 40;

// Režim Začátečník — Radar firem: stejná data jako Valuation Radar, ale jako jednoduchý seznam.
export default function InvestorRadar() {
  const { user, loading: authLoading } = useAuth();
  const { data, error, status } = useRadar();
  const [tab, setTab] = useState<Tab>("cheap");
  const [q, setQ] = useState("");
  const [shown, setShown] = useState(PAGE);

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

  if (authLoading) return <div className="h-40 animate-pulse rounded-2xl bg-panel" />;
  if (!user) return <LoginNeeded what="Radar firem ukazuje, jestli jsou velké firmy levné, nebo drahé vůči tomu, kolik vydělávají — a proč." />;
  if (status === 403) return <PlanNeeded />;
  if (error) return <Card><p className="text-sm text-amber-300">Radar se nepodařilo načíst. Zkus to za chvíli znovu.</p></Card>;
  if (!data) return <div className="space-y-3"><div className="h-12 animate-pulse rounded-2xl bg-panel" /><div className="h-96 animate-pulse rounded-2xl bg-panel" /></div>;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Radar firem</h1>
        <p className="mt-1 text-sm text-gray-400">
          Jak drahé jsou velké firmy vůči tomu, kolik vydělávají a jak rychle rostou. Klikni na firmu a uvidíš proč.
        </p>
      </div>

      <Card>
        <h2 className="mb-2 text-[15px] font-bold text-white">Mapa: kde je která firma</h2>
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
          <ul className="divide-y divide-line">
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
          </ul>
        )}
        {list.length > shown && (
          <div className="border-t border-line px-4 py-3 text-center md:px-5">
            <button onClick={() => setShown((s) => s + PAGE)} className="text-[13px] font-semibold text-neon-soft hover:underline">
              Zobrazit další ({list.length - shown})
            </button>
          </div>
        )}
      </Card>

      <p className="text-[11.5px] leading-relaxed text-gray-500">
        <b className="text-gray-400">Levná</b> = cena je nízko vůči ziskům a jejich růstu, <b className="text-gray-400">Drahá</b> = trh už
        započítal hodně dobrých zpráv. Hodnotí se jen jednotlivé firmy, ne fondy.
        {data.as_of && ` Data k ${dateCs(data.as_of)}.`} Mapu a všechna čísla najdeš v režimu Pokročilý (Valuation Radar).
      </p>
      <Disclaimer>Radar popisuje data (valuace, růst, kvalita, odhady analytiků, trend ceny). Nejde o investiční doporučení.</Disclaimer>
    </div>
  );
}
