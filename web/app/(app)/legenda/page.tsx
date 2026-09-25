"use client";

import { useMemo, useState } from "react";
import { BookOpen, Search } from "lucide-react";

interface Term {
  term: string;
  abbr?: string;
  cat: string;
  desc: string;
  calc?: string;
}

// Kategorie (pořadí = pořadí zobrazení)
const CATS = [
  "Valuation Radar — metriky",
  "Valuation Radar — skóre a verdikty",
  "Gamma (GEX)",
  "Discovery",
  "Smart Money",
  "ORB Radar",
  "Bias & Výhled",
  "Obecné pojmy",
] as const;

const TERMS: Term[] = [
  // ── Valuation Radar — metriky ─────────────────────────────────────────────
  { term: "P/E (trailing)", abbr: "pe_ttm", cat: "Valuation Radar — metriky",
    desc: "Poměr ceny akcie k zisku na akcii za posledních 12 měsíců. Kolik platíš za 1 $ ročního zisku. Nižší = opticky levnější (u ziskových firem).",
    calc: "pe_ttm = cena / EPS_ttm   (EPS_ttm = součet zisku na akcii za poslední 4 kvartály)" },
  { term: "P/E (forward)", abbr: "pe_fwd", cat: "Valuation Radar — metriky",
    desc: "P/E počítané z očekávaného zisku příštích 12 měsíců (z konsenzu analytiků). Bez odhadů se nedopočítá (pak None).",
    calc: "pe_fwd = cena / EPS_ntm (očekávaný zisk na akcii na příštích 12 měsíců)" },
  { term: "Percentil P/E", abbr: "pctile_pe_ttm / pctile_pe_fwd", cat: "Valuation Radar — metriky",
    desc: "Kde leží dnešní P/E v rámci VLASTNÍ historie firmy. 0 = historicky nejlevnější, 100 = nejdražší. Klíčové pro „levné vůči sobě samému“.",
    calc: "percentil = % dní v historii, kdy bylo P/E nižší než dnes" },
  { term: "ROIC", abbr: "roic", cat: "Valuation Radar — metriky",
    desc: "Návratnost investovaného kapitálu — jak efektivně firma vydělává z peněz, které v ní jsou. Vyšší = kvalitnější byznys.",
    calc: "ROIC ≈ provozní zisk po zdanění / investovaný kapitál (dluh + vlastní kapitál)" },
  { term: "Hrubá marže", abbr: "gross_margin", cat: "Valuation Radar — metriky",
    desc: "Podíl hrubého zisku na tržbách. Ukazuje cenovou/značkovou sílu firmy.",
    calc: "gross_margin = hrubý zisk / tržby × 100 %" },
  { term: "Provozní marže", abbr: "operating_margin", cat: "Valuation Radar — metriky",
    desc: "Podíl provozního zisku na tržbách — ziskovost hlavní činnosti před úroky a daněmi.",
    calc: "operating_margin = provozní zisk / tržby × 100 %" },
  { term: "FCF marže", abbr: "fcf_margin", cat: "Valuation Radar — metriky",
    desc: "Kolik z tržeb zůstane jako volný hotovostní tok (peníze po investicích). Kvalitativní ukazatel.",
    calc: "FCF = provozní cash flow − kapitálové výdaje;  fcf_margin = FCF / tržby × 100 %" },
  { term: "Enterprise Value", abbr: "EV / enterprise_value", cat: "Valuation Radar — metriky",
    desc: "Hodnota celé firmy včetně dluhu — cena, za kterou bys koupil celou firmu i s jejími dluhy, minus hotovost.",
    calc: "EV = tržní kapitalizace + čistý dluh" },
  { term: "EV/EBITDA", abbr: "ev_ebitda", cat: "Valuation Radar — metriky",
    desc: "Ocenění firmy vůči provoznímu zisku před odpisy. Srovnává firmy nezávisle na zadlužení a odpisové politice.",
    calc: "EV/EBITDA = enterprise value / EBITDA   (EBITDA = provozní zisk + odpisy a amortizace)" },
  { term: "EV/Sales", abbr: "ev_sales", cat: "Valuation Radar — metriky",
    desc: "Hodnota firmy vůči tržbám. Užitečné u firem bez zisku.",
    calc: "EV/Sales = enterprise value / roční tržby" },
  { term: "P/FCF", abbr: "p_fcf", cat: "Valuation Radar — metriky",
    desc: "Tržní kapitalizace vůči volnému hotovostnímu toku — kolik platíš za 1 $ generované hotovosti.",
    calc: "p_fcf = tržní kapitalizace / FCF_ttm" },
  { term: "PEG (forward)", abbr: "peg_fwd", cat: "Valuation Radar — metriky",
    desc: "P/E vydělené očekávaným růstem zisku. Zohledňuje růst — hodnota kolem 1 se bere jako „férová“, pod 1 levná vůči růstu.",
    calc: "peg_fwd = pe_fwd / očekávaný roční růst EPS (v %)" },
  { term: "Čistý dluh", abbr: "net_debt", cat: "Valuation Radar — metriky",
    desc: "Celkový úročený dluh minus hotovost. Záporný = firma má víc hotovosti než dluhu.",
    calc: "net_debt = celkový dluh − hotovost a ekvivalenty" },
  { term: "Čistý dluh / EBITDA", abbr: "net_debt_to_ebitda", cat: "Valuation Radar — metriky",
    desc: "Zadluženost — kolik let EBITDA by trvalo splatit čistý dluh. Vyšší = rizikovější.",
    calc: "net_debt_to_ebitda = čistý dluh / EBITDA" },
  { term: "Tržní kapitalizace", abbr: "market_cap", cat: "Valuation Radar — metriky",
    desc: "Tržní hodnota všech akcií firmy.",
    calc: "market_cap = cena akcie × počet akcií (diluted)" },
  { term: "Meziroční růst tržeb (TTM)", abbr: "revenue_yoy_ttm", cat: "Valuation Radar — metriky",
    desc: "O kolik % vzrostly tržby za posledních 12 měsíců oproti stejnému období před rokem.",
    calc: "revenue_yoy_ttm = (tržby_TTM / tržby_TTM před rokem − 1) × 100 %" },
  { term: "Meziroční růst EPS (TTM)", abbr: "eps_yoy_ttm", cat: "Valuation Radar — metriky",
    desc: "Meziroční změna zisku na akcii za posledních 12 měsíců.",
    calc: "eps_yoy_ttm = (EPS_TTM / EPS_TTM před rokem − 1) × 100 %" },
  { term: "Očekávaný růst EPS/tržeb (NTM)", abbr: "eps_growth_ntm / revenue_growth_ntm", cat: "Valuation Radar — metriky",
    desc: "Očekávaný růst na příštích 12 měsíců z konsenzu analytiků (NTM = next twelve months). Bez odhadů None.",
    calc: "z konsenzuálních odhadů; bez placeného feedu se nahrazuje trailing hodnotou (nižší confidence)" },
  { term: "Akcelerace růstu", abbr: "growth_accel", cat: "Valuation Radar — metriky",
    desc: "Zrychluje, nebo zpomaluje růst? Kladné = růst nabírá, záporné = ztrácí tempo. Vstup do bubble flagu.",
    calc: "growth_accel = růst v posledním období − růst v předchozím období" },
  { term: "Trend marže", abbr: "margin_trend", cat: "Valuation Radar — metriky",
    desc: "Zlepšuje se, nebo zhoršuje zisková marže v čase.",
    calc: "margin_trend = marže nyní − marže před rokem" },
  { term: "Momentum 12-1", abbr: "mom_12_1", cat: "Valuation Radar — metriky",
    desc: "Cenový výnos za posledních 12 měsíců, ale bez posledního měsíce (klasický akademický momentum faktor — poslední měsíc bývá „reverzní“).",
    calc: "mom_12_1 = výnos ceny za období −12 až −1 měsíc" },
  { term: "Cena vs. SMA200", abbr: "px_vs_sma200", cat: "Valuation Radar — metriky",
    desc: "O kolik % je cena nad/pod 200denním klouzavým průměrem. Nad = uptrend, hluboko pod = downtrend.",
    calc: "px_vs_sma200 = (cena / SMA200 − 1) × 100 %" },
  { term: "Max. pokles za rok", abbr: "max_dd_1y", cat: "Valuation Radar — metriky",
    desc: "Maximální propad od vrcholu k dnu za poslední rok (drawdown). Míra bolestivosti.",
    calc: "max_dd_1y = min. hodnota (cena / dosavadní maximum − 1) za 1 rok" },
  { term: "Realizovaná volatilita 60d", abbr: "realized_vol_60d", cat: "Valuation Radar — metriky",
    desc: "Kolísavost denních výnosů za posledních 60 dní, anualizovaná. Vyšší = rizikovější/rozházenější.",
    calc: "realized_vol_60d = směrodatná odchylka denních výnosů × √252" },
  { term: "Poměr revizí 30d", abbr: "revision_ratio_30d", cat: "Valuation Radar — metriky",
    desc: "Zvyšují, nebo snižují analytici odhady? Kladné = převažují zvýšení. Vstup do bubble flagu.",
    calc: "revision_ratio_30d = (zvýšené − snížené odhady) / celkem, za 30 dní" },
  { term: "Drift odhadů 90d", abbr: "estimate_drift_90d", cat: "Valuation Radar — metriky",
    desc: "O kolik se za 90 dní posunul konsenzuální odhad zisku. Trend očekávání.",
    calc: "estimate_drift_90d = (odhad nyní / odhad před 90 dny − 1) × 100 %" },
  { term: "Průměrné překvapení 4Q", abbr: "avg_surprise_4q", cat: "Valuation Radar — metriky",
    desc: "Jak moc firma v průměru překonává/nedosahuje odhady zisku za poslední 4 kvartály.",
    calc: "avg_surprise_4q = průměr ((skutečný EPS − odhad) / |odhad|) za 4 kvartály" },
  { term: "Změna počtu akcií", abbr: "share_count_change", cat: "Valuation Radar — metriky",
    desc: "Roste, nebo klesá počet akcií? Záporné = zpětné odkupy (dobré pro akcionáře), kladné = ředění.",
    calc: "share_count_change = meziroční změna počtu akcií v %" },
  { term: "Sektorové z-skóre", abbr: "z_pe_fwd / z_ev_ebitda", cat: "Valuation Radar — metriky",
    desc: "Jak moc se metrika liší od typické firmy ve stejné sektorové skupině. Robustní (medián + MAD), aby jedna extrémní firma nerozhodila celek. Potřebuje ≥5 firem ve skupině.",
    calc: "z = (hodnota − medián skupiny) / MAD skupiny, ořezáno na ±3" },

  // ── Valuation Radar — skóre a verdikty ────────────────────────────────────
  { term: "Skóre valuace", abbr: "valuation_score", cat: "Valuation Radar — skóre a verdikty",
    desc: "0–100, jak levně je firma oceněná (kombinace percentilu P/E, EV/EBITDA, PEG, P/FCF…). Vyšší = levnější/atraktivnější.",
    calc: "vážená kombinace ocenění­ových metrik; 0 = drahé, 100 = levné" },
  { term: "Skóre růstu", abbr: "growth_score", cat: "Valuation Radar — skóre a verdikty",
    desc: "0–100, síla a zrychlení růstu tržeb a zisku." },
  { term: "Skóre kvality", abbr: "quality_score", cat: "Valuation Radar — skóre a verdikty",
    desc: "0–100, kvalita byznysu — marže, ROIC, FCF, nízké zadlužení." },
  { term: "Skóre revizí", abbr: "revision_score", cat: "Valuation Radar — skóre a verdikty",
    desc: "0–100, jak se vyvíjejí odhady analytiků (revize, drift, překvapení)." },
  { term: "Skóre trendu", abbr: "trend_score", cat: "Valuation Radar — skóre a verdikty",
    desc: "0–100, cenové momentum a poloha vůči klouzavým průměrům. Nízké = downtrend." },
  { term: "Kompozitní skóre", abbr: "composite_score", cat: "Valuation Radar — skóre a verdikty",
    desc: "Celkové skóre firmy — vážený průměr dílčích skóre. Z něj se počítá horizontální verdikt.",
    calc: "vážený průměr: valuace, růst, kvalita, revize, trend" },
  { term: "Verdikt valuace", abbr: "LEVNÁ / FÉROVÁ / NAPJATÁ / PŘEPÁLENÁ", cat: "Valuation Radar — skóre a verdikty",
    desc: "Slovní shrnutí ocenění dle skóre valuace.",
    calc: "≥70 LEVNÁ · ≥55 FÉROVÁ · ≥40 NAPJATÁ · <40 PŘEPÁLENÁ" },
  { term: "Verdikt horizontu", abbr: "VHODNÁ K DRŽBĚ / SPÍŠE ANO / NEUTRÁLNÍ / SPÍŠE NE", cat: "Valuation Radar — skóre a verdikty",
    desc: "Celkové vyznění dle kompozitního skóre — orientační, ne doporučení.",
    calc: "≥70 VHODNÁ K DRŽBĚ · ≥55 SPÍŠE ANO · ≥40 NEUTRÁLNÍ · <40 SPÍŠE NE" },
  { term: "Bublinová vlajka", abbr: "bubble_flag", cat: "Valuation Radar — skóre a verdikty",
    desc: "Varování „drahé + zpomalující + zhoršující se odhady“ zároveň — typický profil nafouklého ocenění.",
    calc: "percentil P/E fwd > 85  A  akcelerace růstu < 0  A  poměr revizí < 0" },
  { term: "Confidence", abbr: "confidence", cat: "Valuation Radar — skóre a verdikty",
    desc: "Míra důvěry v skóre podle úplnosti a kvality dat. Nižší, když chybí analytické odhady nebo některé metriky." },
  { term: "Unreliable", abbr: "unreliable", cat: "Valuation Radar — skóre a verdikty",
    desc: "Příznak, že datům chybí klíčové vstupy (např. odhady, ROIC) → verdikt ber s rezervou." },

  // ── Gamma (GEX) ───────────────────────────────────────────────────────────
  { term: "Gamma Exposure", abbr: "GEX", cat: "Gamma (GEX)",
    desc: "Dealer gamma z otevřených opčních pozic (open interest). Odhaduje, jak dealeři zajišťováním tlumí nebo zesilují pohyby trhu. Model z veřejného OI, ne přesná pravda.",
    calc: "GEX_strike = gamma × OI × 100 × spot² × 1 %   (call +, put −), sečteno přes všechny striky" },
  { term: "Net GEX (gamma index)", abbr: "net_gex", cat: "Gamma (GEX)",
    desc: "Celkové dealer gamma v $ na 1% pohyb. Kladné = pozitivní režim, záporné = negativní.",
    calc: "součet GEX přes všechny striky při aktuálním spotu" },
  { term: "Pozitivní gamma režim", cat: "Gamma (GEX)",
    desc: "Dealeři pohyby TLUMÍ (prodávají sílu, kupují slabost) → trh spíš mean-revert, klidnější. Výhodné pro fade extrémů." },
  { term: "Negativní gamma režim", cat: "Gamma (GEX)",
    desc: "Dealeři pohyby ZESILUJÍ (kupují sílu, prodávají slabost) → trh trendový, volatilní. Pozor na breakouty." },
  { term: "Gamma flip", abbr: "flip", cat: "Gamma (GEX)",
    desc: "Cenová úroveň, kde net GEX mění znaménko — hranice mezi pozitivním a negativním režimem.",
    calc: "spot, při kterém přepočítané net GEX = 0 (sken hypotetického spotu ±20 %)" },
  { term: "Call wall", cat: "Gamma (GEX)",
    desc: "Strike s největší call gamma — často působí jako rezistence / magnet, kam trh míří.",
    calc: "strike s maximem call GEX" },
  { term: "Put wall", cat: "Gamma (GEX)",
    desc: "Strike s největší put gamma — často působí jako support.",
    calc: "strike s maximem put GEX" },

  // ── Discovery ─────────────────────────────────────────────────────────────
  { term: "Momentum 5d / 20d", abbr: "ret_5d / ret_20d", cat: "Discovery",
    desc: "Cenový výnos za posledních 5 a 20 obchodních dní. Krátkodobá síla pohybu.",
    calc: "ret = (cena dnes / cena před N dny − 1) × 100 %" },
  { term: "Relativní objem", abbr: "rel_vol", cat: "Discovery",
    desc: "Dnešní objem vůči průměru. >1 = obchoduje se víc než obvykle (zájem, zprávy).",
    calc: "rel_vol = dnešní objem / průměrný 20denní objem" },
  { term: "Od 52týdenního high", abbr: "from_high_pct", cat: "Discovery",
    desc: "O kolik % je cena pod ročním maximem. Blízko 0 = u vrcholu (síla)." },
  { term: "Nad SMA20 / SMA50", cat: "Discovery",
    desc: "Zda je cena nad 20/50denním klouzavým průměrem — jednoduchý indikátor krátkodobého/střednědobého trendu." },
  { term: "Discovery skóre", abbr: "score", cat: "Discovery",
    desc: "Kompozit 0–100 zvýrazňující čerstvé momentum + neobvyklý objem blízko 52w high. Heuristika, ne predikce — hlavní hodnota jsou důkazy pod ním.",
    calc: "0.40·momentum 20d + 0.25·momentum 5d + 0.20·rel. objem + 0.15·blízkost 52w high" },
  { term: "Earnings badge", abbr: "days_to_earnings", cat: "Discovery",
    desc: "Počet dní do nejbližšího zveřejnění výsledků + poslední překvapení. Blízké earnings = katalyzátor (žlutě ≤10 dní). Zdroj Finnhub." },

  // ── Smart Money ───────────────────────────────────────────────────────────
  { term: "Insider", cat: "Smart Money",
    desc: "Člen vedení, ředitel nebo >10% vlastník firmy. Musí hlásit obchody s vlastními akciemi SEC (formulář Form 4)." },
  { term: "Form 4", cat: "Smart Money",
    desc: "Regulatorní hlášení SEC o obchodu insidera — veřejné, obvykle do 2 pracovních dnů od obchodu." },
  { term: "Nákup (P) / Prodej (S)", cat: "Smart Money",
    desc: "Transakční kód SEC: P = open-market nákup, S = open-market prodej. Nákupy mají obvykle vyšší signální hodnotu (insideři prodávají z mnoha důvodů — daně, diverzifikace)." },
  { term: "Role insidera", cat: "Smart Money",
    desc: "director (člen představenstva), officer (výkonný manažer + funkce), 10% owner (velký akcionář)." },
  { term: "Hodnota obchodu", cat: "Smart Money",
    desc: "Objem transakce v dolarech.",
    calc: "hodnota = počet akcií × cena za akcii" },

  // ── ORB Radar ─────────────────────────────────────────────────────────────
  { term: "Opening Range", abbr: "ORB", cat: "ORB Radar",
    desc: "Rozpětí (high–low) první svíčky po otevření sessiony (5 nebo 15 min). Sleduje se, jestli a jak se toto rozpětí během dne „sundá“." },
  { term: "Session (Asia / London / NY)", cat: "ORB Radar",
    desc: "Obchodní seance dle času otevření hlavních trhů. Každá má jinou charakteristiku vybírání opening range." },
  { term: "Horizont 30m / 60m / session", cat: "ORB Radar",
    desc: "Za jak dlouho po otevření se měří, zda cena vzala high/low opening range. Na celé session se OR sundá skoro vždy (neinformativní) → edge je na 30/60m." },
  { term: "One-sided / Obě strany / Ani jedna", cat: "ORB Radar",
    desc: "Zda cena v daném horizontu vzala jen jednu stranu OR (one-sided), obě, nebo žádnou. Trend ukazuje, jestli se chování zpevňuje nebo rozpadá." },
  { term: "Break rate", cat: "ORB Radar",
    desc: "Jak často se opening range vůbec prorazí (vzata aspoň jedna strana) v daném horizontu." },

  // ── Bias & Výhled ─────────────────────────────────────────────────────────
  { term: "Denní BIAS", cat: "Bias & Výhled",
    desc: "Směrový náklon dne (LONG/SHORT/NEUTRAL) z AI predikcí dopadu zpráv. Snapshot v 9:00 (London open), předtím průběžný." },
  { term: "Trust score", cat: "Bias & Výhled",
    desc: "Důvěryhodnost biasu 0–100 (síla a konzistence podkladových predikcí). ≥65 vysoká, ≥40 střední, jinak nízká." },
  { term: "Pravděpodobnosti ↑ / → / ↓", abbr: "prob_up / prob_neutral / prob_down", cat: "Bias & Výhled",
    desc: "Rozložení očekávaného směru dne v procentech (nahoru / do strany / dolů)." },
  { term: "Výhledový scénář (hot / inline / cool)", cat: "Bias & Výhled",
    desc: "Pro plánovaný US event: reakce nástroje, když skutečnost vyjde nad forecast (hot), v souladu (inline), nebo pod (cool). Deterministický rule-engine dle typu eventu a instrumentu." },
  { term: "Úspěšnost scénáře", cat: "Bias & Výhled",
    desc: "Jak často predikovaný směr scénáře seděl s realitou (~1h pohyb po eventu). Badge „⌀ 68 % (n=14)“. Actual hodnoty z FRED / ForexFactory." },

  // ── Obecné pojmy ──────────────────────────────────────────────────────────
  { term: "TTM", cat: "Obecné pojmy",
    desc: "Trailing Twelve Months — posledních 12 měsíců (klouzavý roční součet, ne kalendářní rok)." },
  { term: "NTM", cat: "Obecné pojmy",
    desc: "Next Twelve Months — příštích 12 měsíců (forward/očekávané hodnoty)." },
  { term: "Forward vs. trailing", cat: "Obecné pojmy",
    desc: "Trailing = z historických dat. Forward = z očekávání/odhadů do budoucna." },
  { term: "Percentil", cat: "Obecné pojmy",
    desc: "Pořadí hodnoty v rozdělení 0–100. Percentil 20 = hodnota je nižší než 80 % ostatních pozorování." },
  { term: "Z-skóre", cat: "Obecné pojmy",
    desc: "O kolik směrodatných odchylek se hodnota liší od průměru/mediánu skupiny. Umožňuje srovnat různé metriky na jedné škále." },
  { term: "Medián + MAD", cat: "Obecné pojmy",
    desc: "Robustní alternativa k průměru a směrodatné odchylce. MAD = medián absolutních odchylek. Odolné vůči extrémům (jedna divoká firma nerozhodí skupinu)." },
  { term: "SMA (klouzavý průměr)", cat: "Obecné pojmy",
    desc: "Simple Moving Average — průměr ceny za posledních N dní (např. SMA200 = 200denní). Vyhlazuje trend." },
  { term: "Open Interest", abbr: "OI", cat: "Obecné pojmy",
    desc: "Počet otevřených (dosud nevypořádaných) opčních kontraktů na daném striku. Vstup pro výpočet GEX." },
  { term: "Gamma (opce)", cat: "Obecné pojmy",
    desc: "Jak rychle se mění delta opce při pohybu podkladu. Vysoká gamma = zajištění dealerů reaguje prudce → větší vliv na trh." },
  { term: "Volatilita", cat: "Obecné pojmy",
    desc: "Míra kolísavosti ceny. Vyšší volatilita = větší a rychlejší pohyby oběma směry." },
];

function norm(s: string): string {
  return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

// Praktický návod „jak číst gamma“ — highlight nad pojmy v gamma sekci (a na dashboardu v popoveru).
function GammaGuide() {
  return (
    <div className="rounded-xl border border-indigo-900/50 bg-indigo-950/20 p-4 space-y-2.5 text-[13px] leading-relaxed text-gray-300">
      <div className="font-semibold text-indigo-300">Jak číst gamma (kontext k setupu, ne signál)</div>
      <p>
        Gamma ti neříká „kup/prodej“ — říká, <b>jaký charakter dnes trh nejspíš má</b> a <b>kde jsou
        klíčové úrovně</b>. Čti v tomto pořadí:
      </p>
      <p>
        <b>1) Režim (nejdůležitější).</b>{" "}
        <span className="text-green-400 font-medium">Pozitivní gamma</span> = dealeři pohyby tlumí →
        trh rozsahový, mean-revert, klidnější; dipy se vykupují, breakouty spíš selhávají{" "}
        (<i>styl: fadovat extrémy</i>).{" "}
        <span className="text-red-400 font-medium">Negativní gamma</span> = dealeři pohyby zesilují →
        trh trendový, volatilní; momentum funguje, breakouty utíkají (<i>styl: jít s momentem,
        širší stopy</i>).
      </p>
      <p>
        <b>2) Flip = přepínač a pivot.</b> Cena <b>nad flipem</b> = pozitivní/klid, <b>pod flipem</b> =
        negativní/volatilita. Průraz flipu často mění charakter dne — hlídej ho jako klíčovou čáru.
      </p>
      <p>
        <b>3) Walls = magnety.</b> <span className="text-green-300">Call wall</span> = strop/rezistence
        (max call gamma), <span className="text-red-300">Put wall</span> = podlaha/support (max put
        gamma). V pozitivním režimu k nim cena tíhne a zastavuje se.
      </p>
      <p>
        <b>4) Net GEX = síla efektu.</b> Hodně pozitivní = silně „přišpendleno“/klid; kolem nuly nebo
        záporné = nestabilní.
      </p>
      <p className="rounded-lg bg-[#0f1117] border border-[#232735] px-3 py-2 text-gray-400">
        <b className="text-gray-300">Co si vzít:</b> „Jsem nad flipem → pozitivní gamma → dnes spíš
        fadovat rozsah, ne honit breakouty. Klíčová čára je flip; pod ní se to zvrtne v trend/volatilitu,
        u wallů čekej reakci.“
      </p>
      <p className="text-[11px] text-gray-500">
        ⚠️ Model z opčního OI (přes den statický) + konvence dealer/customer — pravděpodobnost, ne jistota.
      </p>
    </div>
  );
}

export default function LegendaPage() {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const needle = norm(q.trim());
    return TERMS.filter((t) => {
      if (cat && t.cat !== cat) return false;
      if (!needle) return true;
      const hay = norm([t.term, t.abbr, t.desc, t.calc].filter(Boolean).join(" "));
      return hay.includes(needle);
    });
  }, [q, cat]);

  const byCat = useMemo(() => {
    const map = new Map<string, Term[]>();
    for (const t of filtered) {
      if (!map.has(t.cat)) map.set(t.cat, []);
      map.get(t.cat)!.push(t);
    }
    return CATS.map((c) => [c, map.get(c) ?? []] as const).filter(([, arr]) => arr.length > 0);
  }, [filtered]);

  const chip = (active: boolean) =>
    `rounded-md px-3 py-1 text-xs font-medium border transition-colors ${
      active ? "bg-[#1e2536] text-white border-[#2f3b55]"
        : "bg-[#151823] text-gray-400 border-[#2a2d3a] hover:text-white"}`;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-950/60 border border-sky-900/50">
            <BookOpen size={16} className="text-sky-400" />
          </span>
          <h1 className="text-2xl font-bold text-white">Legenda</h1>
        </div>
        <p className="text-sm text-gray-400 mt-1">
          Vysvětlivky všech pojmů, zkratek a výpočtů použitých v aplikaci
        </p>
      </div>

      {/* Hledání */}
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Hledat pojem, zkratku nebo význam… (např. P/E, gamma, ROIC, momentum)"
          className="w-full rounded-lg bg-[#151823] border border-[#2a2d3a] pl-10 pr-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-[#2f3b55]"
        />
      </div>

      {/* Kategorie */}
      <div className="flex flex-wrap items-center gap-1.5">
        <button onClick={() => setCat(null)} className={chip(cat === null)}>Vše</button>
        {CATS.map((c) => (
          <button key={c} onClick={() => setCat(cat === c ? null : c)} className={chip(cat === c)}>{c}</button>
        ))}
      </div>

      <div className="text-xs text-gray-500">
        {filtered.length} {filtered.length === 1 ? "pojem" : filtered.length < 5 ? "pojmy" : "pojmů"}
        {q && ` odpovídá „${q}“`}
      </div>

      {byCat.length === 0 && (
        <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-8 text-center text-gray-500 text-sm">
          Nic nenalezeno. Zkus jiný výraz.
        </div>
      )}

      {byCat.map(([category, terms]) => (
        <section key={category} className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-sky-400/80 border-b border-[#2a2d3a] pb-1.5">
            {category}
          </h2>
          {category === "Gamma (GEX)" && <GammaGuide />}
          <div className="grid gap-3 sm:grid-cols-2">
            {terms.map((t) => (
              <div key={t.term} className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-4">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <h3 className="font-semibold text-gray-100">{t.term}</h3>
                  {t.abbr && (
                    <code className="text-[11px] text-sky-300/80 bg-sky-950/40 rounded px-1.5 py-0.5">{t.abbr}</code>
                  )}
                </div>
                <p className="mt-1.5 text-[13px] leading-relaxed text-gray-400">{t.desc}</p>
                {t.calc && (
                  <div className="mt-2 rounded-lg bg-[#0f1117] border border-[#232735] px-2.5 py-1.5">
                    <div className="text-[9px] uppercase tracking-wider text-gray-600 mb-0.5">Výpočet</div>
                    <code className="text-[11px] text-emerald-300/90 leading-relaxed">{t.calc}</code>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}

      <p className="text-[11px] text-gray-600 pt-2">
        Metriky jsou heuristické, počítané z veřejných dat s nejistou kvalitou. Legenda slouží k pochopení
        pojmů — není investiční doporučení.
      </p>
    </div>
  );
}
