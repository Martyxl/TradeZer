"use client";

import { Check, CreditCard } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";

const FREE = ["Živé AI predikce dopadu zpráv", "Denní BIAS a entry plán", "Historie a úspěšnost predikcí"];
const PRO = ["Vše z Free", "Valuation Radar (fundamentální skóre)", "Discovery mode — objevování příležitostí", "Prioritní data z placených feedů"];

export default function PricingPage() {
  const { user } = useAuth();
  const plan = user?.plan ?? "free";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><CreditCard size={20} className="text-[#60ff82]" /> Předplatné</h1>
        <p className="mt-1 text-sm text-gray-400">Feed platí Tradezer — ty jen sbíráš náskok. {user ? `Aktuální plán: ${plan.toUpperCase()}.` : ""}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 max-w-3xl">
        <PlanCard name="Free" price="0 Kč" features={FREE} current={plan === "free"} />
        <PlanCard name="Pro" price="brzy" features={PRO} accent current={plan === "pro"}
          cta={user ? <button disabled className="w-full min-h-10 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.10)] text-sm font-medium text-[#8fffab] opacity-70 cursor-not-allowed">Předplatit (brzy)</button>
                    : <Link href="/registrace" className="block w-full min-h-10 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.10)] text-center leading-10 text-sm font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)]">Vytvořit účet</Link>} />
      </div>

      <p className="text-[11px] text-gray-500 max-w-2xl">
        Platby zatím nejsou spuštěné — Pro funkce jsou během vývoje dostupné všem. Jakmile se platba spustí live,
        objeví se tu předplatné a Valuation Radar se uzamkne pro Free plán.
      </p>
    </div>
  );
}

function PlanCard({ name, price, features, current, accent, cta }: {
  name: string; price: string; features: string[]; current?: boolean; accent?: boolean; cta?: React.ReactNode;
}) {
  return (
    <div className={`rounded-2xl border p-5 ${accent ? "border-[rgba(96,255,130,0.35)] bg-[#0c1a11]" : "border-[#2a2d3a] bg-[#151823]"}`}>
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-white">{name}</h2>
        {current && <span className="rounded bg-[#2a2d3a] px-2 py-0.5 text-[10px] uppercase text-gray-300">Aktuální</span>}
      </div>
      <p className="mt-1 text-2xl font-bold text-white">{price}</p>
      <ul className="mt-4 space-y-2">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-sm text-gray-300"><Check size={15} className="mt-0.5 shrink-0 text-[#60ff82]" /> {f}</li>
        ))}
      </ul>
      {cta && <div className="mt-5">{cta}</div>}
    </div>
  );
}
