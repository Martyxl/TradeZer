"use client";

import Link from "next/link";
import { Lock } from "lucide-react";
import { FREE_ACCESS, PAYWALL_ENABLED, hasAccess, TIER_LABEL, type Tier } from "@/lib/config";
import { useAuth } from "@/lib/auth";

// UX gate pro placené moduly. Skutečné vynucení je SERVER-SIDE (API vrací 403) —
// tohle jen zobrazí upsell místo prázdné/rozbité stránky. `tier` = minimální plán.
export function PaywallGuard({ tier, name, children }: {
  tier: Tier; name: string; children: React.ReactNode;
}) {
  const { user, loading } = useAuth();

  if (!PAYWALL_ENABLED) return <>{children}</>;
  if (loading) return <div className="h-64 animate-pulse rounded-xl bg-[#1a1d27]" />;

  if (hasAccess(user, tier)) return <>{children}</>;

  if (FREE_ACCESS && tier !== "elite") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 rounded-2xl border border-[#2a2d3a] bg-[#151823] p-8 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[rgba(96,255,130,0.12)] text-[#8fffab]">
          <Lock size={22} />
        </div>
        <h2 className="text-lg font-semibold text-white">{name} je zdarma pro registrované</h2>
        <p className="max-w-sm text-sm text-gray-400">
          Celý Tradezer je teď <b className="text-gray-200">zdarma</b>. Stačí si vytvořit účet — bez platební karty.
        </p>
        <div className="flex gap-3">
          <Link href="/registrace"
            className="rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.10)] px-4 py-2 text-sm font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)]">
            Vytvořit účet zdarma
          </Link>
          <Link href="/prihlaseni" className="rounded-lg border border-[#2a2d3a] px-4 py-2 text-sm text-gray-300 hover:text-white">
            Přihlásit se
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 rounded-2xl border border-[#2a2d3a] bg-[#151823] p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[rgba(96,255,130,0.12)] text-[#8fffab]">
        <Lock size={22} />
      </div>
      <h2 className="text-lg font-semibold text-white">{name} je v plánu {TIER_LABEL[tier]}</h2>
      <p className="max-w-sm text-sm text-gray-400">
        Tenhle modul je součástí plánu <b className="text-gray-200">{TIER_LABEL[tier]}</b> a vyšších.
        {user ? " Odemkni si ho v předplatném." : " Vytvoř si účet a odemkni."}
      </p>
      <div className="flex gap-3">
        <Link
          href={user ? "/predplatne" : "/registrace"}
          className="rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.10)] px-4 py-2 text-sm font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)]"
        >
          {user ? "Zobrazit předplatné" : "Vytvořit účet"}
        </Link>
        <Link href="/funkce" className="rounded-lg border border-[#2a2d3a] px-4 py-2 text-sm text-gray-300 hover:text-white">
          Co je v plánech
        </Link>
      </div>
    </div>
  );
}
