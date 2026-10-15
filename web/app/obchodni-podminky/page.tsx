import type { Metadata } from "next";
import Link from "next/link";
import { LegalLayout, Section, UL, ContactEmail, VatNote, ProviderBlock } from "@/components/LegalLayout";

export const metadata: Metadata = {
  title: "Obchodní podmínky — Tradezer",
  description: "Obchodní podmínky služby Tradezer (tradezer.app): plány, platby, předplatné, odstoupení od smlouvy, reklamace.",
};

export default function ObchodniPodminky() {
  return (
    <LegalLayout title="Obchodní podmínky">
      <Section n={1} title="Úvodní ustanovení">
        <ProviderBlock />
        <p>
          Tyto obchodní podmínky upravují vztah mezi Provozovatelem a uživatelem webové služby Tradezer
          dostupné na adrese tradezer.app (dále „Služba“). Řídí se právním řádem České republiky, zejména zákonem
          č. 89/2012 Sb., občanský zákoník, a zákonem č. 634/1992 Sb., o ochraně spotřebitele. Je-li uživatel
          spotřebitelem (fyzická osoba, která jedná mimo rámec své podnikatelské činnosti), nejsou těmito podmínkami
          dotčena jeho zákonná práva.
        </p>
      </Section>

      <Section n={2} title="Charakter Služby — není investiční poradenství">
        <p>
          Tradezer je informační a analytický nástroj: zpravodajství s odhady dopadu na trhy vytvářenými umělou
          inteligencí, tržní statistiky, obchodní a investiční deník, přehled portfolia, valuační a další analýzy a
          simulovaný („paper“) fond „TRADEZER investuje“.
        </p>
        <UL items={[
          <><b className="text-white">Nejde o investiční poradenství ani doporučení</b> ke koupi či prodeji investičních nástrojů. Provozovatel není obchodníkem s cennými papíry ani investičním poradcem a obsah Služby nepředstavuje osobní doporučení ani nabídku.</>,
          "Obchodování a investování (zejména s deriváty, pákovými produkty a CFD) nese riziko ztráty části nebo celé investice. Minulé výsledky ani statistiky nezaručují výsledky budoucí.",
          "Odhady umělé inteligence, semafory, režim trhu a další ukazatele jsou pravděpodobnostní a informativní, mohou být chybné, opožděné nebo neúplné. Rozhodnutí činíš na vlastní odpovědnost.",
          "Fond „TRADEZER investuje“ je simulace s fiktivním kapitálem, slouží k ukázce metodiky; neprobíhají v něm skutečné obchody a nejde o nabídku správy majetku.",
        ]} />
      </Section>

      <Section n={3} title="Uživatelský účet">
        <UL items={[
          "Služba je určena osobám starším 18 let. Registrací uživatel prohlašuje, že je plnoletý.",
          "Pro registraci je nutný platný e-mail a heslo. Uživatel uvádí pravdivé údaje a chrání své přihlašovací údaje.",
          "Účet je osobní — nesmí být sdílen s dalšími osobami ani využíván k přeprodeji přístupu.",
          "Registrací uživatel souhlasí s těmito podmínkami a bere na vědomí Zásady ochrany osobních údajů. Čas a verze souhlasu se uchovávají.",
        ]} />
      </Section>

      <Section n={4} title="Plány a ceny">
        <p>
          Služba je nabízena v plánech Free (zdarma), Trader, Pro a Elite. Aktuální rozsah plánů a ceny jsou uvedeny na
          stránkách <Link href="/funkce" className="text-[#60ff82] hover:underline">Funkce</Link> a{" "}
          <Link href="/predplatne" className="text-[#60ff82] hover:underline">Předplatné</Link>. Ceny jsou uvedeny v amerických
          dolarech (USD) za měsíc, resp. při roční platbě se slevou. Plán označený „Brzy“ není dosud k dispozici.
        </p>
        <p><VatNote /></p>
        <p>
          Provozovatel může rozsah plánů a ceny měnit. Změnu ceny oznámí stávajícím předplatitelům alespoň 30 dnů předem
          a vztahuje se až na další předplatné období; uživatel může před jeho začátkem předplatné zrušit.
        </p>
      </Section>

      <Section n={5} title="Platba a předplatné">
        <UL items={[
          "Platby probíhají přes zpracovatele plateb Stripe Payments Europe, Ltd. Údaje o platební kartě zadává uživatel přímo u Stripe; Provozovatel je neukládá.",
          "Placený plán je předplatné na dobu měsíce nebo roku (dle volby uživatele) a po uplynutí období se automaticky obnovuje za aktuální cenu, dokud ho uživatel nezruší.",
          "Předplatné lze kdykoli zrušit v sekci Účet → Spravovat předplatné nebo e-mailem. Zrušení je účinné ke konci již zaplaceného období, do té doby zůstává přístup zachován. Za již zaplacené období se platba nevrací, nestanoví-li zákon jinak.",
          "Při neúspěšné platbě může být přístup omezen na plán Free. Potvrzení platby a daňový doklad zasílá Stripe na e-mail uživatele.",
          "Služba se poskytuje okamžitě po zaplacení (digitální služba).",
        ]} />
      </Section>

      <Section n={6} title="Odstoupení od smlouvy (spotřebitel)">
        <p>
          Spotřebitel má právo odstoupit od smlouvy o placeném plánu bez udání důvodu do 14 dnů od jejího uzavření
          (§ 1829 a násl. občanského zákoníku). Odstoupení lze oznámit e-mailem na <ContactEmail /> (lze použít jakoukoli
          srozumitelnou formu, vzorový formulář je k dispozici na vyžádání).
        </p>
        <p>
          Při objednávce spotřebitel výslovně žádá o zahájení poskytování Služby před uplynutím lhůty pro odstoupení.
          Odstoupí-li poté od smlouvy, uhradí Provozovateli poměrnou část ceny za dobu, po kterou mu byla Služba
          poskytována; zbývající část ceny Provozovatel vrátí do 14 dnů stejným způsobem, jakým platba přijata.
        </p>
      </Section>

      <Section n={7} title="Reklamace a odpovědnost za vady">
        <UL items={[
          <>Vady Služby (nedostupnost, chybná funkce) lze reklamovat e-mailem na <ContactEmail />. Provozovatel reklamaci vyřídí bez zbytečného odkladu, nejpozději do 30 dnů.</>,
          "Služba pracuje s daty třetích stran (zpravodajství, tržní ceny, makroekonomické údaje), která mohou být zpožděná, neúplná nebo chybná. Provozovatel neručí za jejich správnost a nezaručuje nepřetržitý provoz; plánované odstávky se snaží minimalizovat.",
          "Zákonná práva spotřebitele z vadného plnění digitální služby nejsou těmito podmínkami dotčena.",
        ]} />
      </Section>

      <Section n={8} title="Autorská práva a pravidla užívání">
        <p>
          Software, vzhled, texty, analýzy i zpracovaná data jsou chráněna autorským právem a patří Provozovateli nebo jeho
          poskytovatelům. Uživatel získává nevýhradní, nepřenosnou licenci k osobnímu užívání Služby. Zejména se zakazuje:
        </p>
        <UL items={[
          "automatizované hromadné stahování dat (scraping), jejich přeprodej či zveřejňování,",
          "obcházení omezení plánů nebo zabezpečení Služby,",
          "zatěžování Služby způsobem, který ohrožuje její provoz (včetně zátěžových testů bez souhlasu Provozovatele).",
        ]} />
      </Section>

      <Section n={9} title="Omezení odpovědnosti">
        <p>
          V rozsahu dovoleném právními předpisy Provozovatel neodpovídá za škody či ušlý zisk vzniklé v souvislosti
          s investičními či obchodními rozhodnutími uživatele ani za škodu způsobenou nepřesností dat a odhadů.
          Odpovědnost, kterou nelze zákonem omezit (zejména za újmu na zdraví, úmyslné jednání či hrubou nedbalost, a práva
          spotřebitele), není dotčena.
        </p>
      </Section>

      <Section n={10} title="Ukončení účtu">
        <UL items={[
          "Uživatel může účet kdykoli smazat v sekci Účet → Moje data a soukromí. Smazáním se okamžitě ukončí případné předplatné bez vrácení poměrné části ceny (nestanoví-li zákon jinak) a vymažou se data účtu.",
          "Provozovatel může účet zablokovat nebo zrušit při závažném či opakovaném porušení těchto podmínek, zpravidla po předchozí výzvě.",
        ]} />
      </Section>

      <Section n={11} title="Ochrana osobních údajů">
        <p>
          Zpracování osobních údajů popisují{" "}
          <Link href="/ochrana-osobnich-udaju" className="text-[#60ff82] hover:underline">Zásady ochrany osobních údajů</Link>{" "}
          a informace o ukládání dat v prohlížeči stránka{" "}
          <Link href="/cookies" className="text-[#60ff82] hover:underline">Cookies</Link>.
        </p>
      </Section>

      <Section n={12} title="Mimosoudní řešení sporů">
        <p>
          Spotřebitel se může se sporem ze smlouvy obrátit na Českou obchodní inspekci (Štěpánská 567/15, 120 00 Praha 2,
          coi.cz) jako subjekt mimosoudního řešení spotřebitelských sporů. Dozor nad ochranou osobních údajů vykonává
          Úřad pro ochranu osobních údajů.
        </p>
      </Section>

      <Section n={13} title="Změny podmínek a závěrečná ustanovení">
        <UL items={[
          "Provozovatel může tyto podmínky měnit. Podstatné změny oznámí e-mailem nebo na webu alespoň 30 dnů před účinností; nesouhlasí-li uživatel, může smlouvu ukončit zrušením předplatného či smazáním účtu.",
          "Smluvní vztah se řídí právem České republiky; příslušné jsou soudy České republiky, není-li pro spotřebitele stanoveno jinak.",
          "Tyto podmínky nabývají účinnosti dnem uvedeným v záhlaví.",
        ]} />
      </Section>
    </LegalLayout>
  );
}
