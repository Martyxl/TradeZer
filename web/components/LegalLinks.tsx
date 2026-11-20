import Link from "next/link";
import { LEGAL } from "@/lib/legal";

/** Odkazy na právní stránky + identifikace provozovatele (patička aplikace i úvodní stránky). */
export function LegalLinks({ className = "" }: { className?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 ${className}`}>
      <Link href="/obchodni-podminky" className="hover:text-neon">Obchodní podmínky</Link>
      <Link href="/ochrana-osobnich-udaju" className="hover:text-neon">Ochrana osobních údajů</Link>
      <Link href="/cookies" className="hover:text-neon">Cookies</Link>
      <span>{LEGAL.name}, IČO {LEGAL.ico}</span>
    </div>
  );
}
