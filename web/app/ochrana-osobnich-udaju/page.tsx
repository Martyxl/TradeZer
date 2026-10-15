import type { Metadata } from "next";
import Link from "next/link";
import { LegalLayout, Section, UL, ContactEmail, ProviderBlock } from "@/components/LegalLayout";

export const metadata: Metadata = {
  title: "Ochrana osobních údajů — Tradezer",
  description: "Zásady zpracování osobních údajů (GDPR) služby Tradezer: jaké údaje, proč, komu je předáváme a jaká máš práva.",
};

export default function OchranaUdaju() {
  return (
    <LegalLayout title="Zásady ochrany osobních údajů">
      <Section n={1} title="Správce údajů">
        <ProviderBlock />
        <p>
          Provozovatel je správcem osobních údajů zpracovávaných v rámci služby Tradezer (tradezer.app) ve smyslu
          nařízení (EU) 2016/679 (GDPR) a zákona č. 110/2019 Sb. Zpracováváme jen údaje, které nutně potřebujeme.
        </p>
      </Section>

      <Section n={2} title="Jaké údaje zpracováváme a proč">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-white/15 text-left text-white/60">
                <th className="py-2 pr-4 font-medium">Údaje</th>
                <th className="py-2 pr-4 font-medium">Účel</th>
                <th className="py-2 font-medium">Právní základ</th>
              </tr>
            </thead>
            <tbody className="align-top [&_td]:border-b [&_td]:border-white/10 [&_td]:py-2.5 [&_td]:pr-4">
              <tr><td>E-mail, uživatelské jméno, hash hesla (heslo samotné neukládáme), čas registrace a přihlášení</td><td>Vytvoření a správa účtu, přihlášení, zabezpečení</td><td>Plnění smlouvy (čl. 6 odst. 1 písm. b)</td></tr>
              <tr><td>Plán, stav předplatného, identifikátor zákazníka ve Stripe (údaje o kartě Provozovatel nevidí)</td><td>Poskytnutí placené služby, platby, faktury</td><td>Plnění smlouvy; zákonná povinnost (písm. c)</td></tr>
              <tr><td>Fakturační a účetní záznamy o platbách</td><td>Plnění účetních a daňových povinností (uchování 10 let)</td><td>Zákonná povinnost (písm. c)</td></tr>
              <tr><td>Data, která do služby sám zadáš: záznamy obchodního deníku (instrumenty, ceny, poznámky, odkazy na grafy) a investiční transakce (pozice, nákupy, prodeje, dividendy)</td><td>Chod funkcí deníku, portfolia, statistik a semaforu — vidíš je jen ty</td><td>Plnění smlouvy</td></tr>
              <tr><td>Odkaz na graf (TradingView) a jeho obraz — jen u volitelné funkce AI čtení grafu</td><td>Vytěžení parametrů obchodu do deníku</td><td>Plnění smlouvy</td></tr>
              <tr><td>IP adresa a technické záznamy (logy) zachycené hostingem</td><td>Bezpečnost, ochrana proti zneužití, provoz služby</td><td>Oprávněný zájem (písm. f)</td></tr>
              <tr><td>Souhlas s podmínkami (čas, verze)</td><td>Doložení souhlasu</td><td>Oprávněný zájem; plnění smlouvy</td></tr>
              <tr><td>Anonymní počet návštěv webu (bez identifikace osoby)</td><td>Statistika provozu</td><td>Oprávněný zájem</td></tr>
            </tbody>
          </table>
        </div>
        <p>
          Nezpracováváme údaje pro cílenou reklamu a nepoužíváme sledovací ani marketingové cookies. Žádné
          rozhodování s právními účinky na uživatele neprobíhá výhradně automatizovaně — odhady umělé inteligence jsou
          informativní.
        </p>
      </Section>

      <Section n={3} title="Komu údaje předáváme (zpracovatelé)">
        <UL items={[
          <><b className="text-white">Vercel Inc.</b> — hosting aplikace a webu (funkce běží v regionu Frankfurt).</>,
          <><b className="text-white">Neon, Inc.</b> — databáze, v níž jsou uložena data účtu a deníku.</>,
          <><b className="text-white">Stripe Payments Europe, Ltd.</b> — zpracování plateb a předplatného.</>,
          <><b className="text-white">Resend</b> — odesílání transakčních e-mailů (např. obnova hesla).</>,
          <><b className="text-white">Anthropic, PBC</b> — poskytovatel umělé inteligence. Posíláme mu texty veřejných zpráv k analýze; u volitelné AI funkce čtení grafu též odkaz či obraz grafu, který uživatel zadá. Neposíláme e-mail ani identifikátory účtu.</>,
        ]} />
        <p>
          Někteří zpracovatelé sídlí v USA. Předání do třetích zemí se opírá o rozhodnutí Evropské komise o odpovídající
          ochraně (EU–US Data Privacy Framework) nebo o standardní smluvní doložky. S nikým dalším osobní údaje
          nesdílíme, nepředáváme je k reklamním účelům ani je neprodáváme.
        </p>
      </Section>

      <Section n={4} title="Jak dlouho údaje uchováváme">
        <UL items={[
          "Údaje účtu a data deníku/portfolia — po dobu trvání účtu; po jeho smazání bez zbytečného odkladu vymažeme.",
          "Účetní a daňové doklady — 10 let od konce zdaňovacího období (zákonná povinnost; uchovává je i Stripe).",
          "Technické logy hostingu — krátkodobě podle nastavení poskytovatele.",
        ]} />
      </Section>

      <Section n={5} title="Tvá práva">
        <p>Máš právo na přístup, opravu, výmaz, omezení zpracování, přenositelnost a vznést námitku. Většinu z nich vyřídíš sám v účtu:</p>
        <UL items={[
          <><b className="text-white">Export všech svých dat</b> (JSON): <Link href="/ucet" className="text-[#60ff82] hover:underline">Účet → Moje data a soukromí</Link>.</>,
          <><b className="text-white">Smazání účtu a dat</b>: tamtéž. Aktivní předplatné se tím ukončí.</>,
          <>Ostatní žádosti pošli na <ContactEmail />; odpovíme nejpozději do 30 dnů.</>,
        ]} />
        <p>
          Máš také právo podat stížnost u dozorového úřadu: Úřad pro ochranu osobních údajů, Pplk. Sochora 27, 170 00 Praha 7,
          uoou.gov.cz.
        </p>
      </Section>

      <Section n={6} title="Zabezpečení">
        <p>
          Hesla ukládáme pouze jako výsledek jednosměrného hašování, komunikace probíhá šifrovaně (HTTPS), přístup k datům je
          omezen a data zálohuje poskytovatel databáze. Žádný systém není dokonale bezpečný; v případě porušení zabezpečení,
          které by ohrozilo tvá práva, tě i dozorový úřad budeme informovat v souladu s GDPR.
        </p>
      </Section>

      <Section n={7} title="Cookies a úložiště prohlížeče">
        <p>
          Používáme pouze nezbytné úložiště prohlížeče (přihlášení, nastavení). Podrobnosti najdeš na stránce{" "}
          <Link href="/cookies" className="text-[#60ff82] hover:underline">Cookies</Link>.
        </p>
      </Section>

      <Section n={8} title="Změny zásad">
        <p>
          Zásady můžeme aktualizovat; o podstatných změnách tě informujeme e-mailem nebo na webu. Aktuální verze je vždy na
          této stránce.
        </p>
      </Section>
    </LegalLayout>
  );
}
