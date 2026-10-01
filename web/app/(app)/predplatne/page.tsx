"use client";

import { useEffect, useState } from "react";
import { Check, CreditCard, Loader2 } from "lucide-react";
import Link from "next/link";
import { useAuth, authHeaders } from "@/lib/auth";
import { PLANS, ANNUAL_DISCOUNT, annualPerMonth, annualTotal, type Plan } from "@/lib/plans";

async function postJson(path: string): Promise<{ url?: string; detail?: string }> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({}),
  });
  return res.json().catch(() => ({}));
}

export default function PricingPage() {
  const { user } = useAuth();
  const plan = user?.plan ?? "free";
  const [annual, setAnnual] = useState(false);
  const [banner, setBanner] = useState<"success" | "cancel" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // Které tiery jdou reálně koupit (mají nastavený Stripe price). Dokud Stripe
  // není nakonfigurovaný, zůstane prázdné a tlačítka ukážou "brzy".
  const [buyable, setBuyable] = useState<Record<string, { month?: boolean; year?: boolean }>>({});

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("checkout");
    if (q === "success" || q === "cancel") {
      setBanner(q);
      window.history.replaceState({}, "", "/predplatne");
    }
    fetch("/api/billing/config")
      .then((r) => r.json())
      .then((d) => setBuyable(d?.buyable ?? {}))
      .catch(() => setBuyable({}));
  }, []);

  async function handleBuy(tier: string) {
    setErr(null);
    setBusy(tier);
    try {
      const res = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ tier, interval: annual ? "year" : "month" }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok && d.url) {
        window.location.href = d.url;
      } else {
        setErr(d.detail || "Platbu se nepodařilo spustit. Zkus to prosím znovu.");
        setBusy(null);
      }
    } catch {
      setErr("Chyba připojení. Zkus to prosím znovu.");
      setBusy(null);
    }
  }

  async function openPortal() {
    setErr(null);
    setBusy("portal");
    try {
      const d = await postJson("/api/billing/portal");
      if (d.url) window.location.href = d.url;
      else {
        setErr(d.detail || "Správu předplatného se nepodařilo otevřít.");
        setBusy(null);
      }
    } catch {
      setErr("Chyba připojení.");
      setBusy(null);
    }
  }

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

      {banner === "success" && (
        <div className="rounded-lg border border-[rgba(96,255,130,0.4)] bg-[#0c1a11] px-4 py-3 text-sm text-[#8fffab]">
          ✓ Platba proběhla. Předplatné se aktivuje během pár sekund — po obnovení stránky uvidíš nový plán.
        </div>
      )}
      {banner === "cancel" && (
        <div className="rounded-lg border border-[#2a2d3a] bg-[#151823] px-4 py-3 text-sm text-gray-300">
          Platba zrušena — nic jsme ti nestrhli. Kdykoli to můžeš zkusit znovu.
        </div>
      )}
      {err && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/[0.07] px-4 py-3 text-sm text-red-300">
          {err}
        </div>
      )}

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
          <PlanCard
            key={p.id}
            plan={p}
            annual={annual}
            current={plan === p.id}
            loggedIn={!!user}
            buyable={!!buyable[p.id]?.[annual ? "year" : "month"]}
            busy={busy === p.id}
            onBuy={() => handleBuy(p.id)}
            onManage={openPortal}
            managing={busy === "portal"}
          />
        ))}
      </div>

      <p className="text-[11px] text-gray-500 max-w-2xl">
        Platby zajišťuje Stripe — karty a fakturační údaje zadáváš u něj, Tradezer je nevidí.
        Roční platba = sleva {Math.round(ANNUAL_DISCOUNT * 100)} %. Předplatné lze kdykoli zrušit ve správě účtu.
      </p>
    </div>
  );
}

function PlanCard({ plan, annual, current, loggedIn, buyable, busy, onBuy, onManage, managing }: {
  plan: Plan; annual: boolean; current: boolean; loggedIn: boolean;
  buyable: boolean; busy: boolean; onBuy: () => void; onManage: () => void; managing: boolean;
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
          free ? (
            <Link href="/dashboard"
              className="block w-full rounded-lg border border-[#2a2d3a] bg-[#1a1d27] py-2.5 text-center text-sm text-gray-200 hover:border-gray-500">
              Přejít na dashboard
            </Link>
          ) : (
            <button onClick={onManage} disabled={managing}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#2a2d3a] bg-[#1a1d27] py-2.5 text-sm text-gray-200 hover:border-gray-500 disabled:opacity-60">
              {managing && <Loader2 size={14} className="animate-spin" />} Spravovat předplatné
            </button>
          )
        ) : free ? (
          <Link href={loggedIn ? "/dashboard" : "/registrace"}
            className="block w-full rounded-lg border border-[#2a2d3a] bg-[#1a1d27] py-2.5 text-center text-sm text-gray-200 hover:border-gray-500">
            {loggedIn ? "Přejít na dashboard" : "Vytvořit účet zdarma"}
          </Link>
        ) : !loggedIn ? (
          <Link href="/registrace"
            className={`block w-full rounded-lg py-2.5 text-center text-sm font-medium ${
              accent ? "border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] text-[#8fffab]" : "border border-[#2a2d3a] bg-[#1a1d27] text-gray-200"
            } hover:opacity-90`}>
            Vyzkoušet
          </Link>
        ) : !buyable ? (
          <div className="w-full rounded-lg border border-[#2a2d3a] py-2.5 text-center text-sm text-gray-500">
            Brzy
          </div>
        ) : (
          <button onClick={onBuy} disabled={busy}
            className={`flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-medium ${
              accent ? "border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] text-[#8fffab]" : "border border-[#2a2d3a] bg-[#1a1d27] text-gray-200"
            } hover:opacity-90 disabled:opacity-60`}>
            {busy && <Loader2 size={14} className="animate-spin" />} Předplatit
          </button>
        )}
      </div>
    </div>
  );
}
