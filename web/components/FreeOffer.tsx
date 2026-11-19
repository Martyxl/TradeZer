// Nabídka v režimu „vše zdarma“: jedna karta se vším + zašedlá Elite (připravujeme, nejde koupit).
import Link from "next/link";
import { Check } from "lucide-react";
import { EliteBadge } from "@/components/EliteSoon";
import { ELITE_PLAN, FREE_ALL_FEATURES } from "@/lib/plans";

export function FreeOffer({ ctaHref = "/registrace", ctaLabel = "Vytvořit účet zdarma" }: {
  ctaHref?: string | null; ctaLabel?: string;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1.7fr_1fr]">
      <div className="relative flex flex-col rounded-2xl border border-[#60ff82]/40 bg-[#0c1a11] p-6">
        <span className="absolute -top-2.5 left-6 rounded-full bg-[#60ff82] px-2.5 py-0.5 text-[10px] font-bold uppercase text-[#06120a]">
          Vše odemčeno
        </span>
        <h3 className="text-lg font-semibold text-white">Tradezer</h3>
        <p className="text-xs text-white/50">Celá aplikace, žádné placené úrovně</p>
        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-4xl font-bold text-white">Zdarma</span>
          <span className="text-sm text-white/50">stačí účet, bez platební karty</span>
        </div>
        <ul className="mt-5 grid flex-1 gap-2 sm:grid-cols-2">
          {FREE_ALL_FEATURES.map((f) => (
            <li key={f} className="flex items-start gap-2 text-[13px] text-white/80">
              <Check size={15} className="mt-0.5 shrink-0 text-[#60ff82]" /> {f}
            </li>
          ))}
        </ul>
        {ctaHref && (
          <Link href={ctaHref}
            className="mt-6 block rounded-lg bg-[#60ff82] py-2.5 text-center text-sm font-semibold text-[#06120a] hover:opacity-90">
            {ctaLabel}
          </Link>
        )}
      </div>
      <div className="flex flex-col rounded-2xl border border-white/10 bg-white/[0.02] p-6">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold text-white/60">{ELITE_PLAN.name}</h3>
          <EliteBadge />
        </div>
        <p className="text-xs text-white/40">{ELITE_PLAN.tagline}</p>
        <ul className="mt-5 flex-1 space-y-2 opacity-60">
          {ELITE_PLAN.features.filter((f) => !f.startsWith("Vše z")).map((f) => (
            <li key={f} className="flex items-start gap-2 text-[13px] text-white/60">
              <Check size={15} className="mt-0.5 shrink-0 text-white/30" /> {f}
            </li>
          ))}
        </ul>
        <p className="mt-5 text-[11px] leading-relaxed text-white/40">
          Funkce máme hotové, chybí licence na živá data. Až ji budeme mít, dáme vědět.
        </p>
      </div>
    </div>
  );
}
