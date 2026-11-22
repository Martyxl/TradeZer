"use client";

import Link from "next/link";
import { ShieldCheck, TrendingDown, TrendingUp } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useIdeas, fmtCzk, dateCs } from "@/components/investor/data";
import { BrokerButtons, BrokerNote, Card, CLASS_COLOR, Disclaimer, LoginNeeded } from "@/components/investor/ui";
import type { Idea } from "@/components/investor/types";

const VERDICT_CLS: Record<string, string> = {
  "LEVNÁ": "bg-emerald-950/60 text-emerald-300", "FÉROVÁ": "bg-emerald-950/40 text-emerald-300",
  "NAPJATÁ": "bg-amber-950/50 text-amber-300", "PŘEPÁLENÁ": "bg-red-950/50 text-red-300",
};
const VERDICT_CS: Record<string, string> = { "LEVNÁ": "Levná", "FÉROVÁ": "Férová cena", "NAPJATÁ": "Napjatá", "PŘEPÁLENÁ": "Přepálená" };

function IdeaRow({ it }: { it: Idea }) {
  const v = it.verdict ?? "";
  return (
    <li className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
      <span className={`mt-0.5 w-[86px] shrink-0 rounded-full px-2 py-0.5 text-center text-[11.5px] font-semibold ${VERDICT_CLS[v] ?? "bg-raised text-gray-300"}`}>
        {VERDICT_CS[v] ?? (it.kind === "expensive" ? "Předražená" : "—")}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <Link href={`/valuation?ticker=${encodeURIComponent(it.ticker)}`} className="font-semibold text-white hover:underline">{it.ticker}</Link>
          <span className="truncate text-[12px] text-gray-500">{it.name}</span>
        </div>
        {it.text && <p className="text-[13px] text-gray-300">{it.text}</p>}
        {it.tags.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {it.tags.map((t) => <span key={t} className="rounded-full bg-blue-950/50 px-2 py-px text-[11px] text-blue-300">{t}</span>)}
          </div>
        )}
      </div>
    </li>
  );
}

// Režim Začátečník — Nápady: bezpečný základ (široké ETF) + levné kvalitní / předražené firmy z Valuation Radaru.
export default function InvestorIdeas() {
  const { user, loading: authLoading } = useAuth();
  const { data, error } = useIdeas();

  if (authLoading) return <div className="h-40 animate-pulse rounded-2xl bg-panel" />;
  if (!user) return <LoginNeeded what="Nápady ukazují bezpečný základ portfolia (široké fondy, zlato, dluhopisy) a firmy, které vycházejí levně nebo předraženě." />;
  if (error) return <Card><p className="text-sm text-amber-300">Nápady se nepodařilo načíst. Zkus to za chvíli znovu.</p></Card>;
  if (!data) return <div className="space-y-4"><div className="h-80 animate-pulse rounded-2xl bg-panel" /><div className="h-60 animate-pulse rounded-2xl bg-panel" /></div>;

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-white">Nápady</h1>

      <Card>
        <div className="flex items-start gap-2.5">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-neon" />
          <div>
            <h2 className="text-[15px] font-bold text-white">Bezpečný základ portfolia</h2>
            <p className="text-[13px] text-gray-400">Široké fondy na dlouhé roky. Kupuj je pravidelně a výkyvy neřeš — v Přehledu uvidíš, kolik do kterého dát.</p>
          </div>
        </div>
        <ul className="mt-3 divide-y divide-line">
          {data.base.map((u) => (
            <li key={u.symbol} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-bold text-white">{u.short}</span>
                  <span className="flex items-center gap-1 text-[12px] text-gray-400"><span className="h-2 w-2 rounded-full" style={{ background: CLASS_COLOR[u.cls] }} />{u.class_label}</span>
                  {u.held && <span className="rounded-full bg-emerald-950/60 px-2 py-px text-[11px] text-emerald-300">máš v portfoliu</span>}
                </div>
                <p className="text-[13px] text-gray-200">{u.what}</p>
                <p className="text-[12px] text-gray-500">
                  {u.role} · poplatek fondu ~{u.ter.toLocaleString("cs-CZ")} % ročně
                  {u.price != null && <> · cena {u.price.toLocaleString("cs-CZ", { maximumFractionDigits: 2 })} {u.price_currency}{u.price_czk ? ` (≈ ${fmtCzk(u.price_czk)})` : ""}</>}
                </p>
                <p className="text-[11px] text-gray-600">{u.name} · Xetra: {u.symbol}</p>
              </div>
              <div className="flex shrink-0 gap-1.5"><BrokerButtons size="sm" /></div>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11.5px] text-gray-500">Všechny fondy jsou akumulační (dividendy reinvestují, nemusíš je danit každý rok) a obchodují se v EUR na burze Xetra. Poplatky orientačně — před nákupem si přečti dokument klíčových informací (KID).</p>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <h2 className="flex items-center gap-2 text-[15px] font-bold text-white"><TrendingUp size={16} className="text-neon" /> Levné kvalitní firmy</h2>
          <p className="mb-3 text-[12.5px] text-gray-500">Pro část plánu „Vlastní akcie“. Jedna firma max 10 % portfolia.</p>
          {data.cheap.length ? <ul className="divide-y divide-line">{data.cheap.map((i) => <IdeaRow key={i.ticker} it={i} />)}</ul>
            : <p className="text-sm text-gray-500">Teď žádná firma nesplňuje přísná kritéria (levná vůči své historii, rostoucí zisky, spolehlivá data).</p>}
        </Card>
        <Card>
          <h2 className="flex items-center gap-2 text-[15px] font-bold text-white"><TrendingDown size={16} className="text-[#ff5050]" /> Pozor, předražené</h2>
          <p className="mb-3 text-[12.5px] text-gray-500">Teď spíš nepřikupovat. Pokud je držíš s velkým ziskem, zvaž odebrání části.</p>
          {data.expensive.length ? <ul className="divide-y divide-line">{data.expensive.map((i) => <IdeaRow key={i.ticker} it={i} />)}</ul>
            : <p className="text-sm text-gray-500">Žádná sledovaná firma teď není výrazně předražená.</p>}
        </Card>
      </div>
      {data.as_of && <p className="-mt-2 text-[11.5px] text-gray-500">Valuace k {dateCs(data.as_of)} · podrobnosti a mapa v <Link href="/valuation" className="underline hover:text-gray-300">Valuation Radaru</Link>.</p>}

      <Card>
        <h2 className="text-[15px] font-bold text-white">Kde nakoupit</h2>
        <p className="mb-3 text-[13px] text-gray-400">Fondy i akcie z této stránky koupíš u obou brokerů. Kupuj skutečné ETF a akcie, ne CFD.</p>
        <div className="flex flex-wrap gap-2"><BrokerButtons /></div>
        <div className="mt-3"><BrokerNote /></div>
      </Card>

      <Disclaimer>Výběr fondů a firem je edukativní přehled z veřejných dat a pravidel Valuation Radaru, ne investiční doporučení. Minulá výkonnost nezaručuje budoucí výnosy.</Disclaimer>
    </div>
  );
}
