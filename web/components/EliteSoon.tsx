// Funkce, které umíme, ale chybí k nim licence dat (Elite, zatím se neprodává): zašedlá ukázka
// + štítek. Ukázka je ilustrační (žádná skutečná čísla), jen aby bylo vidět, co funkce dělá.
import { Lock } from "lucide-react";

export function EliteBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">
      <Lock size={10} /> Elite · připravujeme
    </span>
  );
}

/** Obal ukázky: obsah zašedlý, neklikatelný, nečitelný pro čtečky (je jen ilustrační). */
export function EliteGhost({ children }: { children: React.ReactNode }) {
  return (
    <div aria-hidden className="pointer-events-none select-none opacity-40 grayscale blur-[1.5px]">
      {children}
    </div>
  );
}
