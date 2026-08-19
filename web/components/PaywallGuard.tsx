"use client";

import Link from "next/link";
import { Lock } from "lucide-react";
import { PAYWALL_VALUATION } from "@/lib/config";
import { useAuth } from "@/lib/auth";

// Gate pro placené záložky. Když je flag vypnutý, vždy pustí dál (vývoj odemčeně).
// Až se spustí live: přepni PAYWALL_VALUATION=true → Free uvidí upsell místo obsahu.
export function PaywallGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (!PAYWALL_VALUATION) return <>{children}</>;
  if (loading) return <div className="h-64 animate-pulse rounded-xl bg-[#1a1d27]" />;

  const isPro = user?.plan === "pro" || user?.is_admin;
  if (isPro) return <>{children}</>;

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 rounded-2xl border border-[#2a2d3a] bg-[#151823] p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[rgba(96,255,130,0.12)] text-[#8fffab]"><Lock size={22} /></div>
      <h2 className="text-lg font-semibold text-white">Valuation Radar je součást Pro</h2>
      <p className="max-w-sm text-sm text-gray-400">Fundamentální skóre, valuační percentily a objevování příležitostí jsou dostupné v Pro plánu.</p>
      <div className="flex gap-3">
        {user
          ? <Link href="/predplatne" className="rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.10)] px-4 py-2 text-sm font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)]">Zobrazit předplatné</Link>
          : <Link href="/registrace" className="rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.10)] px-4 py-2 text-sm font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)]">Vytvořit účet</Link>}
      </div>
    </div>
  );
}
