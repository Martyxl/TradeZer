import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { LEGAL } from "@/lib/legal";

/** Rozložení veřejných právních stránek (VOP, Zásady, Cookies) v brandu Neon Candles. */
export function LegalLayout({ title, updated, children }: { title: string; updated?: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#060a0c] text-white" style={{ fontFamily: "var(--font-inter), Inter, system-ui, sans-serif" }}>
      <nav className="mx-auto flex max-w-3xl items-center gap-4 px-5 py-4 sm:px-8">
        <Link href="/" className="flex items-center gap-2 text-[15px] text-white/80 hover:text-[#60ff82]">
          <ArrowLeft size={16} /> tradezer
        </Link>
        <div className="ml-auto flex items-center gap-4 text-sm">
          <Link href="/prihlaseni" className="text-white/70 hover:text-white">Přihlásit</Link>
        </div>
      </nav>
      <main className="mx-auto max-w-3xl px-5 pb-16 pt-6 sm:px-8">
        <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-white/50">Účinné od {updated ?? LEGAL.effectiveFrom} · verze {LEGAL.termsVersion}</p>
        <div className="mt-8 space-y-8 text-[15px] leading-7 text-white/80">{children}</div>
        <LegalNav />
      </main>
    </div>
  );
}

export function LegalNav() {
  return (
    <div className="mt-14 flex flex-wrap gap-x-5 gap-y-2 border-t border-white/10 pt-6 text-sm text-white/55">
      <Link href="/obchodni-podminky" className="hover:text-[#60ff82]">Obchodní podmínky</Link>
      <Link href="/ochrana-osobnich-udaju" className="hover:text-[#60ff82]">Ochrana osobních údajů</Link>
      <Link href="/cookies" className="hover:text-[#60ff82]">Cookies</Link>
    </div>
  );
}

export function Section({ n, title, children }: { n?: number; title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 text-lg font-semibold text-white">{n ? `${n}. ` : ""}{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

export function UL({ items }: { items: React.ReactNode[] }) {
  return <ul className="list-disc space-y-1.5 pl-6">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>;
}

/** Kontaktní e-mail (nebo výrazná výzva k doplnění, dokud není vyplněn v lib/legal.ts). */
export function ContactEmail() {
  return LEGAL.email
    ? <a className="text-[#60ff82] hover:underline" href={`mailto:${LEGAL.email}`}>{LEGAL.email}</a>
    : <mark className="rounded bg-amber-500/20 px-1.5 text-amber-300">[doplnit kontaktní e-mail]</mark>;
}

export function VatNote() {
  if (LEGAL.vatPayer === true) return <>Ceny jsou uvedeny včetně DPH, je-li stanovena zákonem.</>;
  if (LEGAL.vatPayer === false) return <>Provozovatel není plátcem DPH, ceny jsou konečné.</>;
  return <mark className="rounded bg-amber-500/20 px-1.5 text-amber-300">[doplnit: plátce / neplátce DPH]</mark>;
}

export function ProviderBlock() {
  return (
    <p>
      <b className="text-white">{LEGAL.name}</b>, IČO {LEGAL.ico}, místo podnikání {LEGAL.address} (dále „Provozovatel“).
      Kontakt: <ContactEmail />.
    </p>
  );
}
