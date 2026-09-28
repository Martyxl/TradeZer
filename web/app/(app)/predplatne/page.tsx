"use client";

import { useState } from "react";
import { Check, CreditCard } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { PLANS, ANNUAL_DISCOUNT, annualPerMonth, annualTotal, type Plan } from "@/lib/plans";

export default function PricingPage() {
  const { user } = useAuth();
  const plan = user?.plan ?? "free";
  const [annual, setAnnual] = useState(false);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
          <CreditCard size={20} className="text-[#60ff82]" /> Předplatné
        </h1>
        <p className="mt-1 text-sm text-gray-400">
          Feed platí Tradezer — ty jen sbíráš náskok.{user ? ` Aktuální plán: ${plan.toUpperCase()}.` : ""}
        </p>
      </div>

      {/* Přepínač měsíčně / ročně */}
      <div className="inline-flex items-center gap-1 rounded-lg border border-[#2a2d3a] bg-[#151823] p-1 text-sm">
        <button onClick={() => setAnnual(false)}
          className={`rounded-md px-3 py-1.5 transition-colors ${!annual ? "bg-[#1e2536] text-white" : "text-gray-400 hover:text-white"}`}>
          Měsíčně
        </button>
        <button onClick={() => setAnnual(true)}
          className={`rounded-md px-3 py-1.5 transition-colors ${annual ? "bg-[#1e2536] text-white" : "text-gray-400 hover:text-white"}`}>
          Ročně <span className="text-[#8fffab]">−{Math.round(ANNUAL_DISCOUNT * 100)} %</span>
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {PLANS.map((p) => (
          <PlanCard key={p.id} plan={p} annual={annual} current={plan === p.id} loggedIn={!!user} />
        ))}
      </div>

      <p className="text-[11px] text-gray-500 max-w-2xl">
        Platby zatím nejsou spuštěné — placené funkce jsou během vývoje dostupné všem. Jakmile se
        platba spustí live, objeví se tu předplatné a zamčené moduly se odemknou podle plánu.
        Roční platba = sleva {Math.round(ANNUAL_DISCOUNT * 100)} %.
      </p>
    </div>
  );
}

function PlanCard({ plan, annual, current, loggedIn }: {
  plan: Plan; annual: boolean; current: boolean; loggedIn: boolean;
}) {
  const free = plan.priceUsd === 0;
  const accent = plan.highlight;
  const price = free ? "$0" : annual ? `$${annualPerMonth(plan.priceUsd)}` : `$${plan.priceUsd}`;
  const border = plan.soon ? "border-amber-500/40 bg-amber-500/[0.05]" : accent ? "border-[rgba(96,255,130,0.4)] bg-[#0c1a11]" : "border-[#2a2d3a] bg-[#151823]";

  return (
    <div className={`relative rounded-2xl border p-5 flex flex-col ${border}`}>
      {accent && (
        <span className="absolute -top-2.5 left-5 rounded-full bg-[#60ff82] px-2.5 py-0.5 text-[10px] font-bold uppercase text-[#06120a]">
          Doporučeno
        </span>
      )}
      {plan.soon && (
        <span className="absolute -top-2.5 left-5 rounded-full bg-amber-400 px-2.5 py-0.5 text-[10px] font-bold uppercase text-[#1a1200]">
          Brzy
        </span>
      )}
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-white">{plan.name}</h2>
        {current && <span className="rounded bg-[#2a2d3a] px-2 py-0.5 text-[10px] uppercase text-gray-300">Aktuální</span>}
      </div>
      <p className="text-xs text-gray-500">{plan.tagline}</p>

      <div className="mt-3">
        <span className="text-3xl font-bold text-white">{price}</span>
        {!free && <span className="text-sm text-gray-500"> / měsíc</span>}
        {!free && annual && (
          <div className="text-[11px] text-[#8fffab]">${annualTotal(plan.priceUsd)} ročně — ušetříš {Math.round(ANNUAL_DISCOUNT * 100)} %</div>
        )}
        {!free && !annual && <div className="text-[11px] text-gray-600">nebo ${annualTotal(plan.priceUsd)} ročně (−{Math.round(ANNUAL_DISCOUNT * 100)} %)</div>}
      </div>

      <ul className="mt-4 space-y-2 flex-1">
        {plan.features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-[13px] text-gray-300">
            <Check size={15} className="mt-0.5 shrink-0 text-[#60ff82]" /> {f}
          </li>
        ))}
      </ul>

      <div className="mt-5">
        {plan.soon ? (
          <div className="w-full rounded-lg border border-amber-500/30 bg-amber-500/10 py-2.5 text-center text-sm font-medium text-amber-300">
            Připravujeme
          </div>
        ) : current ? (
          <button disabled className="w-full rounded-lg border border-[#2a2d3a] py-2.5 text-sm text-gray-400 opacity-70 cursor-default">
            Máš aktivní
          </button>
        ) : free ? (
          <Link href={loggedIn ? "/dashboard" : "/registrace"}
            className="block w-full rounded-lg border border-[#2a2d3a] bg-[#1a1d27] py-2.5 text-center text-sm text-gray-200 hover:border-gray-500">
            {loggedIn ? "Přejít na dashboard" : "Vytvořit účet zdarma"}
          </Link>
        ) : (
          <button disabled={loggedIn}
            className={`block w-full rounded-lg py-2.5 text-center text-sm font-medium ${
              accent ? "border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] text-[#8fffab]" : "border border-[#2a2d3a] bg-[#1a1d27] text-gray-200"
            } ${loggedIn ? "opacity-70 cursor-not-allowed" : "hover:opacity-90"}`}>
            {loggedIn ? "Předplatit (brzy)" : (
              <Link href="/registrace" className="block">Vyzkoušet</Link>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
