import type { Metadata } from "next";
import Link from "next/link";
import { LegalLayout, Section } from "@/components/LegalLayout";

export const metadata: Metadata = {
  title: "Cookies a úložiště — Tradezer",
  description: "Jaké údaje Tradezer ukládá ve tvém prohlížeči. Žádné sledovací ani reklamní cookies.",
};

const ROWS: { name: string; where: string; purpose: string; kind: string; ttl: string }[] = [
  { name: "tz_token", where: "localStorage", purpose: "Udržení přihlášení (podepsaný přístupový token)", kind: "Nezbytné", ttl: "do odhlášení" },
  { name: "tz_visit_counted", where: "sessionStorage", purpose: "Aby se návštěva v jedné relaci započítala do anonymního počítadla jen jednou", kind: "Nezbytné/provozní", ttl: "do zavření karty" },
  { name: "tz_notice_ok", where: "localStorage", purpose: "Zapamatování, že jsi zavřel/a informační lištu o úložišti", kind: "Funkční", ttl: "trvale (do smazání)" },
  { name: "tz_denik_engine", where: "localStorage", purpose: "Zapamatování zvoleného enginu AI čtení grafu v deníku (jen pro správce)", kind: "Funkční", ttl: "trvale (do smazání)" },
];

export default function Cookies() {
  return (
    <LegalLayout title="Cookies a úložiště prohlížeče">
      <Section title="Stručně">
        <p>
          Tradezer <b className="text-white">nepoužívá analytické, marketingové ani sledovací cookies</b> a žádné
          reklamní nástroje třetích stran. Ukládáme ve tvém prohlížeči jen to, co je nezbytné pro přihlášení a základní
          nastavení. Protože jde o nezbytné a funkční úložiště, není k němu potřeba souhlas; přesto o něm informujeme.
        </p>
      </Section>

      <Section title="Co ukládáme">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-white/15 text-left text-white/60">
                <th className="py-2 pr-4 font-medium">Název</th>
                <th className="py-2 pr-4 font-medium">Kde</th>
                <th className="py-2 pr-4 font-medium">Účel</th>
                <th className="py-2 pr-4 font-medium">Typ</th>
                <th className="py-2 font-medium">Doba</th>
              </tr>
            </thead>
            <tbody className="align-top [&_td]:border-b [&_td]:border-white/10 [&_td]:py-2.5 [&_td]:pr-4">
              {ROWS.map((r) => (
                <tr key={r.name}>
                  <td><code className="text-[#8fffab]">{r.name}</code></td><td>{r.where}</td><td>{r.purpose}</td><td>{r.kind}</td><td>{r.ttl}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Třetí strany">
        <p>
          Při platbě jsi přesměrován/a na stránky <b className="text-white">Stripe</b>, který používá vlastní cookies nezbytné
          pro zabezpečení plateb a prevenci podvodů (viz zásady Stripe). Tradezer s nimi nepracuje.
        </p>
      </Section>

      <Section title="Jak úložiště smazat">
        <p>
          Údaje můžeš kdykoli odstranit v nastavení prohlížeče (smazání dat webu tradezer.app) nebo odhlášením. Smazáním
          přihlašovacího tokenu se odhlásíš. Zpracování osobních údajů popisují{" "}
          <Link href="/ochrana-osobnich-udaju" className="text-[#60ff82] hover:underline">Zásady ochrany osobních údajů</Link>.
        </p>
      </Section>

      <Section title="Do budoucna">
        <p>
          Pokud někdy přidáme nástroje, které souhlas vyžadují (např. analytiku), zobrazíme před jejich zapnutím volbu
          a bez tvého výslovného souhlasu je nespustíme.
        </p>
      </Section>
    </LegalLayout>
  );
}
