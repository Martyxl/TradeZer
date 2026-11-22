"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, CalendarDays, ThumbsDown, ThumbsUp } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useCompany, dateCs } from "@/components/investor/data";
import { BrokerButtons, Card, Disclaimer, KindPill, LoginNeeded } from "@/components/investor/ui";
import { BucketPill, PillarCard, PlanNeeded } from "@/components/investor/radar";

const ADVICE_LABEL = { buy: "Kandidát na nákup", hold: "Držet / nespěchat", wait: "Teď nekupovat", trim: "Zvážit prodej části" } as const;

// Režim Začátečník — zjednodušená karta firmy: verdikt, 5 otázek, důvody pro/proti, co to znamená pro mě.
export default function InvestorCompany() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker || "").toUpperCase();
  const { user, loading: authLoading } = useAuth();
  const { data: d, error, status } = useCompany(ticker);

  const back = (
    <Link href="/investor/radar" className="inline-flex items-center gap-1 text-[13px] text-gray-400 hover:text-white">
      <ArrowLeft size={14} /> Radar firem
    </Link>
  );

  if (authLoading) return <div className="h-40 animate-pulse rounded-2xl bg-panel" />;
  if (!user) return <LoginNeeded what="Karta firmy vysvětlí jednoduše, jestli je firma levná nebo drahá a proč." />;
  if (status === 403) return <div className="space-y-4">{back}<PlanNeeded /></div>;
  if (status === 404) return (
    <div className="space-y-4">{back}<Card><p className="text-sm text-gray-300">Firmu <b className="text-white">{ticker}</b> Radar nesleduje — hodnotí jen vybrané velké firmy, ne fondy.</p></Card></div>
  );
  if (error) return <div className="space-y-4">{back}<Card><p className="text-sm text-amber-300">Kartu firmy se nepodařilo načíst. Zkus to za chvíli znovu.</p></Card></div>;
  if (!d) return <div className="space-y-4">{back}<div className="h-40 animate-pulse rounded-2xl bg-panel" /><div className="h-72 animate-pulse rounded-2xl bg-panel" /></div>;

  const kind = d.advice.kind;
  return (
    <div className="space-y-5">
      {back}

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-white">{d.ticker}</h1>
            <p className="text-sm text-gray-400">{d.name}{d.sector ? ` · ${d.sector}` : ""}</p>
          </div>
          <BucketPill bucket={d.bucket} label={d.verdict_label} big />
        </div>
        <p className="mt-3 text-[15px] font-semibold text-white">{d.headline}</p>
        {d.overall && <p className="text-[13.5px] text-gray-300">{d.overall}</p>}
        {!d.reliable && (
          <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-950/40 px-3 py-2 text-[12.5px] text-amber-300">
            Data k firmě jsou neúplná{d.reliability_note ? ` (${d.reliability_note})` : ""} — hodnocení ber s rezervou.
          </p>
        )}
      </Card>

      <Card className={kind === "buy" ? "border-[rgba(96,255,130,0.35)]" : ""}>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-[15px] font-bold text-white">Co to znamená pro tebe</h2>
          <KindPill kind={kind === "trim" ? "trim" : kind === "wait" ? "wait" : kind === "buy" ? "buy" : "hold"} label={ADVICE_LABEL[kind]} />
          {d.held && d.weight != null && <span className="text-[12px] text-gray-500">máš ji · {d.weight.toLocaleString("cs-CZ", { maximumFractionDigits: 1 })} % portfolia</span>}
        </div>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-gray-300">{d.advice.text}</p>
        {kind === "buy" && <div className="mt-3 flex flex-wrap gap-1.5"><BrokerButtons size="sm" /></div>}
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {d.pillars.map((p) => <PillarCard key={p.key} p={p} />)}
      </div>

      {(d.pros.length > 0 || d.cons.length > 0) && (
        <div className="grid gap-3 md:grid-cols-2">
          <Card>
            <h2 className="flex items-center gap-2 text-[15px] font-bold text-white"><ThumbsUp size={15} className="text-neon" /> Co mluví pro</h2>
            {d.pros.length ? (
              <ul className="mt-2 space-y-1.5 text-[13px] text-gray-300">{d.pros.map((t) => <li key={t} className="flex gap-2"><span className="text-neon">+</span>{t}</li>)}</ul>
            ) : <p className="mt-2 text-[13px] text-gray-500">Nic výrazného.</p>}
          </Card>
          <Card>
            <h2 className="flex items-center gap-2 text-[15px] font-bold text-white"><ThumbsDown size={15} className="text-[#ff5050]" /> Co mluví proti</h2>
            {d.cons.length ? (
              <ul className="mt-2 space-y-1.5 text-[13px] text-gray-300">{d.cons.map((t) => <li key={t} className="flex gap-2"><span className="text-[#ff5050]">−</span>{t}</li>)}</ul>
            ) : <p className="mt-2 text-[13px] text-gray-500">Nic výrazného.</p>}
          </Card>
        </div>
      )}

      {d.next_earnings && (
        <p className="flex items-center gap-2 text-[13px] text-gray-300">
          <CalendarDays size={14} className="text-gray-500" />
          Další výsledky zveřejní {dateCs(d.next_earnings)} — kolem nich bývá cena rozkolísaná, s nákupem klidně počkej až po nich.
        </p>
      )}

      <p className="text-[11.5px] text-gray-500">
        {d.as_of && `Data k ${dateCs(d.as_of)}. `}
        Všechna čísla, graf a výsledky po čtvrtletích jsou v plném{" "}
        <Link href={`/valuation?ticker=${encodeURIComponent(d.ticker)}`} className="underline hover:text-gray-300">Valuation Radaru</Link>.
      </p>
      <Disclaimer>Karta popisuje data Valuation Radaru srozumitelnými slovy. Nejde o investiční doporučení — rozhodnutí je vždy na tobě.</Disclaimer>
    </div>
  );
}
