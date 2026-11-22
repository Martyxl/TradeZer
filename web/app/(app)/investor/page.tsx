"use client";

import Link from "next/link";
import { ArrowRight, RefreshCw } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { usePlan, fmtCzk, fmtPct } from "@/components/investor/data";
import { ActionList, Card, Disclaimer, LoginNeeded, MarketCards, Stat } from "@/components/investor/ui";

// Režim Začátečník — Přehled: režim trhu + nálada a jeden seznam „Co teď udělat".
export default function InvestorHome() {
  const { user, loading: authLoading } = useAuth();
  const { data, error, loading, reload } = usePlan();

  if (authLoading) return <div className="h-40 animate-pulse rounded-2xl bg-panel" />;
  if (!user) return <LoginNeeded what="Přehled ti řekne, co teď udělat se svým portfoliem — podle plánu, který si zvolíš. Stačí účet zdarma." />;
  if (error) return (
    <Card>
      <p className="text-sm text-amber-300">Přehled se nepodařilo načíst. Zkus to za chvíli znovu.</p>
      <Link href="/investor/portfolio" className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-neon-soft hover:underline">Moje portfolio — zapsat nákup / import <ArrowRight size={13} /></Link>
    </Card>
  );
  if (!data) return <div className="space-y-4"><div className="h-32 animate-pulse rounded-2xl bg-panel" /><div className="h-64 animate-pulse rounded-2xl bg-panel" /></div>;

  const t = data.totals;
  const empty = data.positions.length === 0;
  const upPct = t.invested ? (t.unrealized / t.invested) * 100 : null;

  return (
    <div className="space-y-5">
      <MarketCards market={data.market} />

      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-lg font-bold text-white">Co teď udělat</h1>
            <p className="text-[12.5px] text-gray-500">
              Typ <b className="text-gray-300">{data.profile.plan === "custom" ? "Vlastní" : data.profile.plans[data.profile.plan as "careful"]?.label}</b>
              {" "}· k investování teď <b className="text-gray-300">{fmtCzk(data.invest_now.total)}</b>
              {data.invest_now.capital > 0 && ` (vklad ${fmtCzk(data.invest_now.monthly)} + volné ${fmtCzk(data.invest_now.capital)})`}
              {" "}· <Link href="/investor/portfolio" className="underline hover:text-gray-300">změnit</Link>
            </p>
          </div>
          <button onClick={reload} disabled={loading} className="flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-[12.5px] text-gray-300 hover:text-white disabled:opacity-50">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Obnovit
          </button>
        </div>
        {!data.profile.plan_set && !empty && (
          <div className="mb-4 rounded-xl border border-[rgba(96,255,130,0.3)] bg-neon-tint p-3 text-[13px] text-gray-300">
            Nákupy teď počítáme podle výchozího typu. Vyber si svůj (opatrný až agresivní) a zadej volné peníze —{" "}
            <Link href="/investor/portfolio" className="inline-flex items-center gap-1 font-semibold text-neon-soft hover:underline">nastavit <ArrowRight size={13} /></Link>
          </div>
        )}
        {data.invest_now.hint && (
          <p className="mb-4 rounded-xl border border-line bg-sunken p-3 text-[13px] text-gray-300">{data.invest_now.hint}</p>
        )}
        {empty && (
          <div className="mb-4 rounded-xl border border-line bg-sunken p-3 text-[13px] text-gray-300">
            Zatím tu nemáš žádné pozice. Začni třemi kroky: <b className="text-white">1)</b> zvol si plán,{" "}
            <b className="text-white">2)</b> založ účet u brokera, <b className="text-white">3)</b> každý měsíc kup, co ti tu vyjde,
            a nákup zapiš (nebo nahraj výpis z XTB).{" "}
            <Link href="/investor/portfolio" className="inline-flex items-center gap-1 font-semibold text-neon-soft hover:underline">Nastavit plán <ArrowRight size={13} /></Link>
          </div>
        )}
        <ActionList actions={data.actions} onChanged={reload} />
      </Card>

      {!empty && (
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Hodnota portfolia" value={fmtCzk(t.value + (t.reserve || 0))} sub={t.reserve ? `včetně rezervy ${fmtCzk(t.reserve)}` : undefined} />
          <Stat label="Zisk / ztráta" value={fmtCzk(t.unrealized)} sub={fmtPct(upPct)}
            tone={t.unrealized > 0 ? "text-neon" : t.unrealized < 0 ? "text-[#ff5050]" : "text-white"} />
          <Stat label="Bez daně už teď" value={fmtCzk(t.tax_free)} sub="drženo přes 3 roky" />
        </div>
      )}

      <Disclaimer />
    </div>
  );
}
