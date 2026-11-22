"use client";

import { Compass, LayoutDashboard } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useMode } from "@/lib/mode";

/** Jednorázová volba režimu po přihlášení (dokud ji uživatel neudělá). Kdykoli jde změnit v horní liště. */
export function ModeOnboarding() {
  const { user } = useAuth();
  const { unset, ready, setMode } = useMode();
  if (!user || !ready || !unset) return null;
  const opt = "flex flex-1 items-start gap-3 rounded-xl border border-line bg-sunken p-3.5 text-left transition-colors hover:border-[rgba(96,255,130,0.5)]";
  return (
    <section aria-label="Volba režimu" className="mb-6 rounded-2xl border border-[rgba(96,255,130,0.3)] bg-neon-tint p-4 md:p-5">
      <h2 className="text-[15px] font-bold text-white">Jak chceš Tradezer používat?</h2>
      <p className="mt-0.5 text-[13px] text-gray-400">Volbu můžeš kdykoli změnit přepínačem v horní liště.</p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <button type="button" className={opt} onClick={() => setMode("simple")}>
          <Compass size={20} className="mt-0.5 shrink-0 text-neon" />
          <span>
            <span className="block font-semibold text-white">Začátečník</span>
            <span className="block text-[12.5px] text-gray-400">Chci jen vědět, co koupit nebo prodat, a mít přehled o svém portfoliu a daních.</span>
          </span>
        </button>
        <button type="button" className={opt} onClick={() => setMode("pro", { navigate: false })}>
          <LayoutDashboard size={20} className="mt-0.5 shrink-0 text-[#60b4ff]" />
          <span>
            <span className="block font-semibold text-white">Pokročilý</span>
            <span className="block text-[12.5px] text-gray-400">Vím, co hledám — chci zprávy, trading, valuace, smart money a všechna data.</span>
          </span>
        </button>
      </div>
    </section>
  );
}
