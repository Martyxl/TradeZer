"use client";

import { useState } from "react";
import Link from "next/link";
import {
  LayoutDashboard, Activity, NotebookPen, Sunrise, History, BarChart3, Target,
  Telescope, Landmark, BookOpen, Check, ArrowLeft, type LucideIcon,
} from "lucide-react";
import { MODULES, PLANS, ANNUAL_DISCOUNT, annualPerMonth, annualTotal, type TierId } from "@/lib/plans";

const ICONS: Record<string, LucideIcon> = {
  LayoutDashboard, Activity, NotebookPen, Sunrise, History, BarChart3, Target, Telescope, Landmark, BookOpen,
};

const TIER_META: Record<TierId, { label: string; cls: string }> = {
  free: { label: "Free", cls: "text-gray-300 border-white/20 bg-white/5" },
  trader: { label: "Trader · $5", cls: "text-[#8fffab] border-[#60ff82]/40 bg-[#60ff82]/10" },
  pro: { label: "Pro · $15", cls: "text-amber-300 border-amber-500/40 bg-amber-500/10" },
};

export default function FunkcePage() {
  const [annual, setAnnual] = useState(false);

  return (
    <div className="min-h-screen bg-[#060a0c] text-white" style={{ fontFamily: "var(--font-inter), Inter, system-ui, sans-serif" }}>
      {/* Nav */}
      <nav className="mx-auto flex max-w-6xl items-center gap-4 px-5 py-4 sm:px-8">
        <Link href="/" className="flex items-center gap-2 text-[15px] text-white/80 hover:text-[#60ff82]">
          <ArrowLeft size={16} /> tradezer
        </Link>
        <div className="ml-auto flex items-center gap-4 text-sm">
          <Link href="/prihlaseni" className="text-white/70 hover:text-white">Přihlásit</Link>
          <Link href="/registrace" className="rounded bg-[#60ff82] px-4 py-2 font-semibold text-[#06120a] hover:opacity-90">
            Vytvořit účet
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <header className="mx-auto max-w-6xl px-5 pt-10 pb-8 sm:px-8">
        <span className="text-[13px] uppercase tracking-[0.06em] text-[#60ff82]">Co všechno umím</span>
        <h1 className="mt-3 text-3xl font-medium leading-tight sm:text-5xl">
          Jedna appka. Celý tvůj <span className="text-[#7dffa0]">edge</span>.
        </h1>
        <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-white/70">
          AI predikce dopadu zpráv, gamma levely, fundamentální valuace, screener příležitostí i insider
          aktivita — vše na jednom místě. Níže je kompletní přehled modulů a v jakém plánu je najdeš.
        </p>
      </header>

      {/* Moduly */}
      <section className="mx-auto max-w-6xl px-5 pb-12 sm:px-8">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((m) => {
            const Icon = ICONS[m.icon] ?? LayoutDashboard;
            const tm = TIER_META[m.tier];
            return (
              <div key={m.name} className="flex flex-col rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#60ff82]/30 bg-[#60ff82]/10">
                    <Icon size={17} className="text-[#7dffa0]" />
                  </span>
                  <h3 className="font-semibold text-white">{m.name}</h3>
                  <span className={`ml-auto rounded-full border px-2 py-0.5 text-[10px] font-medium ${tm.cls}`}>{tm.label}</span>
                </div>
                <p className="mt-2.5 text-[13px] leading-relaxed text-white/65">{m.desc}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Pricing */}
      <section id="cenik" className="mx-auto max-w-6xl px-5 pb-16 sm:px-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <span className="text-[13px] uppercase tracking-[0.06em] text-[#60ff82]">Plány</span>
            <h2 className="mt-2 text-2xl font-medium sm:text-3xl">Zaplať jednou, sbírej náskok</h2>
          </div>
          <div className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-white/[0.04] p-1 text-sm">
            <button onClick={() => setAnnual(false)}
              className={`rounded-md px-3 py-1.5 ${!annual ? "bg-white/10 text-white" : "text-white/60 hover:text-white"}`}>Měsíčně</button>
            <button onClick={() => setAnnual(true)}
              className={`rounded-md px-3 py-1.5 ${annual ? "bg-white/10 text-white" : "text-white/60 hover:text-white"}`}>
              Ročně <span className="text-[#8fffab]">−{Math.round(ANNUAL_DISCOUNT * 100)} %</span>
            </button>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          {PLANS.map((p) => {
            const free = p.priceUsd === 0;
            const price = free ? "$0" : annual ? `$${annualPerMonth(p.priceUsd)}` : `$${p.priceUsd}`;
            return (
              <div key={p.id} className={`relative flex flex-col rounded-2xl border p-6 ${p.highlight ? "border-[#60ff82]/40 bg-[#0c1a11]" : "border-white/10 bg-white/[0.03]"}`}>
                {p.highlight && (
                  <span className="absolute -top-2.5 left-6 rounded-full bg-[#60ff82] px-2.5 py-0.5 text-[10px] font-bold uppercase text-[#06120a]">Doporučeno</span>
                )}
                <h3 className="text-lg font-semibold">{p.name}</h3>
                <p className="text-xs text-white/50">{p.tagline}</p>
                <div className="mt-3">
                  <span className="text-4xl font-bold">{price}</span>
                  {!free && <span className="text-sm text-white/50"> / měsíc</span>}
                  {!free && (
                    <div className="text-[11px] text-white/50">
                      {annual ? <span className="text-[#8fffab]">${annualTotal(p.priceUsd)} ročně — ušetříš {Math.round(ANNUAL_DISCOUNT * 100)} %</span>
                              : <>nebo ${annualTotal(p.priceUsd)} ročně (−{Math.round(ANNUAL_DISCOUNT * 100)} %)</>}
                    </div>
                  )}
                </div>
                <ul className="mt-5 flex-1 space-y-2">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-[13px] text-white/80">
                      <Check size={15} className="mt-0.5 shrink-0 text-[#60ff82]" /> {f}
                    </li>
                  ))}
                </ul>
                <Link href="/registrace"
                  className={`mt-6 block rounded-lg py-2.5 text-center text-sm font-semibold ${
                    p.highlight ? "bg-[#60ff82] text-[#06120a] hover:opacity-90" : "border border-white/20 bg-white/5 text-white hover:border-white/40"
                  }`}>
                  {free ? "Začít zdarma" : "Vyzkoušet"}
                </Link>
              </div>
            );
          })}
        </div>

        <p className="mt-6 text-[11px] text-white/40">
          Platby se spouští brzy — během vývoje jsou placené moduly dostupné všem. Roční platba = sleva {Math.round(ANNUAL_DISCOUNT * 100)} %.
          Obchodování nese riziko; výhoda ho jen zmenšuje.
        </p>
      </section>

      <footer className="border-t border-white/10">
        <div className="mx-auto max-w-6xl px-5 py-8 text-[13px] text-white/50 sm:px-8">
          tradezer.app — AI, se kterou se nehádáš.
        </div>
      </footer>
    </div>
  );
}
