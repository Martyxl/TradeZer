"""Popisy stránek Tradezeru pro chatovacího pomocníka (co stránka ukazuje a jak ji číst).

Klíč = první segment cesty (např. "/discovery"). Doplňuje Legendu (glossary.json), která vysvětluje
jednotlivé pojmy a vzorce. Při přidání/změně stránky aktualizovat i tady.
"""

OVERVIEW = """Tradezer (tradezer.app) je česká aplikace pro tradery a investory. AI (jazykový model) čte ekonomické
zprávy a kalendář a odhaduje jejich dopad na trhy; k tomu nabízí screenery a nástroje pro investice.
Sledované trhy: NQ (Nasdaq 100 futures), ES (S&P 500), YM (Dow Jones), XAUUSD (zlato), EURUSD, GBPUSD, USDJPY.
Menu má skupiny Trading (Deník, Historie, ORB Radar, Statistiky) a Investice (Investice, Daně, TRADEZER investuje,
Valuation Radar, Discovery, Smart Money, Dark Pool). Některé moduly jsou v placených plánech (Trader, Pro).
Přepínač v horní liště mění režim: Pokročilý = celé menu výše; Začátečník = jen 4 stránky pod /investor
(Přehled s Radarem firem, Moje portfolio, Nápady, Tradezer investuje) se signály podle vlastního investičního plánu.
Vše je edukativní analýza z veřejných dat — NENÍ to investiční doporučení."""

PAGES: dict[str, str] = {
    "/investor": """Režim Začátečník (přepínač Začátečník / Pokročilý v horní liště; volba se pamatuje na účtu).
Čtyři stránky místo celé aplikace:
- Přehled (/investor): režim trhu a nálada investorů (0–100, strach ↔ chamtivost) jednou větou, co to znamená, a seznam
  „Co teď udělat“: Koupit (rozdělení měsíčního vkladu do částí portfolia, které jsou pod cílem plánu — rebalancování
  vkladem bez prodeje), Zvážit prodej části (jednotlivá akcie s červeným semaforem nebo nad 20 % portfolia — návrh
  vrátit váhu k 10 %), Počkej (důvod ubrat je, ale do 90 dnů bude nákup osvobozen od daně), Nad plánem, Daně
  (blížící se osvobození), Držet. Pod tím Sezónnost: pro každé aktivum ze seznamu graf posledních 3 let (každý rok
  jedna čára = % od začátku ledna, svislá čára = dnešek) a kolik se v minulých letech změnilo od dnešního data do
  konce roku — jen historie, ne předpověď. Úplně dole Radar firem (viz níže).
- Moje portfolio (/investor/portfolio): investiční typ Opatrný (40 % akciové fondy, 35 % dluhopisy, 15 % zlato,
  10 % rezerva), Vyvážený (60/15/10, 15 % vlastní akcie), Dynamický (65 % fondy, 5 % zlato, 30 % vlastní akcie),
  Agresivní (55 % fondy, 45 % vlastní akcie) nebo Vlastní; dotazník 4 otázek typ doporučí (krátký horizont nebo
  prodej při propadu → opatrnější typ). Volné peníze k investování (jednorázově; nákupy zapsané po zadání se od nich
  samy odečítají), měsíční vklad a rezerva mimo brokera. Nákupy = vklad + volné peníze; malé položky pod 500 Kč se
  slučují, u portfolia pod 50 000 Kč jde díl vlastních akcií do širokého fondu, větší nákup akcií se dělí mezi až
  3 firmy. Rozložení vs. cíl, pozice se štítkem a datem, odkdy jsou bez daně (3 roky).
  Zápis nákupu a import výpisu z XTB; data jsou stejná jako v Investicích.
- Nápady (/investor/napady): bezpečný základ — VWCE (FTSE All-World), SXR8 (S&P 500), EUNL (MSCI World),
  IS3N (rozvíjející se trhy), 4GLD (fyzické zlato), EUNA (globální dluhopisy v EUR), XEON (peněžní trh); vše akumulační
  UCITS ETF na Xetře. Dále levné kvalitní firmy (nákupní zóna Valuation Radaru se spolehlivými daty) a předražené.
  Odkazy na brokery XTB a eToro (mohou být partnerské). Kupovat skutečné ETF/akcie, ne CFD.
- Radar firem (sekce na Přehledu /investor#radar, tarif Trader jako Valuation Radar; mapa zón + seznam): firmy z Valuation Radaru rozdělené na Levné /
  Férová cena / Drahé / Moje firmy, hledání. Klik na firmu (/investor/radar/TICKER) = zjednodušená karta: verdikt
  jednou větou, 5 otázek se semaforem (Cena — je levná?, Růst, Kvalita, Analytici, Trend) s vysvětlením z metrik,
  „Co mluví pro / proti“ (hnací faktory skóre lidsky), datum dalších výsledků a „Co to znamená pro tebe“ podle
  verdiktu, váhy v portfoliu a investičního typu. Odkazy na firmu vedou sem z Nápadů, Moje portfolio i Přehledu.
- Tradezer investuje (/investor/fond): zjednodušený pohled na ukázkový AI fond — výnos vs. S&P 500, co drží, poslední tahy.
Pravidla jsou transparentní a vychází z plánu, který si uživatel zvolí — NENÍ to investiční doporučení.""",
    "/dashboard": """Dashboard — hlavní přehled pro zvolený instrument (přepínač tickerů nahoře).
- Zprávy: proud ekonomických zpráv a událostí z kalendáře; u každé AI odhad pravděpodobnosti pohybu instrumentu
  nahoru / do strany (neutral) / dolů v následujících ~30 minutách a důležitost zprávy. Reakce se měří od ceny těsně
  před zprávou; u vydaných makro dat (např. „194K vs 200K expected“) od plánovaného času vydání.
- BIAS: denní směrový náklon (LONG/SHORT/NEUTRAL) složený z predikcí zpráv obchodního dne; snapshot po London open
  (07:00 UTC). Pondělní bias zahrnuje i zprávy z víkendu. Karta ukazuje historickou úspěšnost biasu
  (NY session, 95% interval; „≈ náhoda“ = neliší se od 50 %) — dřívější trust score se ukázalo jako nespolehlivé.
- Entry karta: plán vstupu po NY open (13:30 UTC) — limit proti směru biasu o offset, drženo do NY close; ukazuje
  i reálnou úspěšnost tohoto plánu z minulých dní.
- Výhled (Outlook): dnešní plánované US události a scénáře hot / inline / cool (co se stane, když číslo vyjde nad /
  v souladu / pod očekávání).
- Gamma karta: dealer gamma z opčního trhu (režim, flip, call/put wall) — kontext, ne signál.
- Režim trhu: klid / napětí / panika / stabilizace podle VIX, S&P, ropy a závažnosti světových zpráv.
Přesnost odhadů se ukazuje poctivě na stránce Historie; na běžné zprávy je směrový signál zatím slabý, nejlépe AI
funguje u vydaných makro dat.""",
    "/history": """Historie predikcí — jak přesné jsou AI odhady dopadu zpráv.
- Trefa směru: kolikrát model trefil směr, když tipl nahoru/dolů a trh se opravdu pohnul (náhoda = 50 %).
- Korelace s pohybem (IC): souvislost mezi odhadem (pravděpodobnost nahoru − dolů) a skutečným 30min pohybem;
  0 = žádný signál, ≥ 0,05 užitečné.
- Přesnost (3 třídy) se musí srovnávat se „základem“ = podíl nejčastějšího výsledku (obvykle „neutral“, kolem 60 %);
  přesnost pod základem neznamená nutně špatný model, model, který by vždy tipoval neutral, by měl přesnost = základ.
- Přepínač Běžné reakce / Gap: gap = zprávy při zavřeném trhu (víkend, noc), měřeno jako skok při znovuotevření —
  jiné měřítko, proto odděleně.
- Matice záměn, bias analýza (co model nadhodnocuje) a přesnost podle kategorie zprávy.""",
    "/denik": """Deník — obchodní deník: zapisuješ obchody (instrument, směr long/short, vstup, SL, TP, výstup, výsledek
win/lose, poznámky) a sleduješ, co ti reálně funguje. Import z CSV. AI čtení obchodu ze screenshotu TradingView
je zatím jen pro admina („Coming soon“ pro ostatní).""",
    "/orb": """ORB Radar — statistiky Opening Range Breakout: rozpětí první 5/15min svíčky po otevření session (Asia,
London, NY) a jak často cena během 30/60 minut nebo celé session vezme jeho high, low, obě strany nebo nic.
Plovoucí okno ukazuje, jestli se chování zpevňuje nebo rozpadá. Zdarma. Pro forex jsou data zatím jen z posledních
~60 obchodních dní (Yahoo), u indexů a zlata delší historie.""",
    "/stats": """Statistiky — tržní statistiky z 5min dat: velikost session (Asia/London/NY), kde se tiskne
denní high/low, návraty k dennímu open, nPOC, VWAP, týdenní vzory, volatilita a objem po hodinách, ORB.
Jednotky: body u indexů a zlata, pipy u forexu. Sekce „Trading — živé výsledky entry plánu“ ukazuje SKUTEČNÉ výsledky
den po dni (bias po London open → limit po NY open → drženo do close): počet obchodů, úspěšnost, průměr na obchod,
součet a průkaznost t-stat (pod 2 = může to být jen náhoda). Data se přepočítávají každý měsíc.""",
    "/investice": """Investice — vlastní portfolio: transakce (nákupy, prodeje, dividendy), import CSV, živá hodnota
pozic v CZK, zisk/ztráta, vývoj hodnoty v čase a u akcií semafor s verdiktem z Valuation Radaru.""",
    "/dane": """Daně — pomocník pro české daně z akcií: časový test (osvobození po 3 letech držení), které nákupy kdy
splní test a co by se danilo při prodeji. Orientační výpočet, ne daňové poradenství.""",
    "/fond": """TRADEZER investuje — ukázkový modelový fond řízený pravidly a AI: nakupuje firmy, které Valuation Radar
hodnotí jako levné nebo férové, s ohledem na režim trhu (v panice nekupuje „padající nůž“, nevyprodává). Horizont
3+ roky, prodává jen výjimečně (rozbitá teze), mimo jiné kvůli daňovému časovému testu. Ukazuje pozice, obchody,
poznámky ke každému rozhodnutí a výkon proti benchmarku. Jen ukázka, ne nabídka investice.""",
    "/valuation": """Valuation Radar — fundamentální ocenění amerických akcií: bublinová mapa (osa X =
percentil forward P/E vůči vlastní historii firmy, osa Y = očekávaný růst zisku, velikost = tržní kapitalizace,
barva = verdikt). Překrývající se bubliny se slučují do kolečka s počtem — kliknutím se zobrazí seznam firem.
Skóre valuace, růstu, kvality, revizí, trendu a kompozitní skóre 0–100, verdikty LEVNÁ/FÉROVÁ/NAPJATÁ/PŘEPÁLENÁ a
bublinová vlajka. Firmu lze přidat polem nahoře (ticker nebo název).
Rozhodovací zóny na mapě: nad zelenou čárou „nákupní zóna (k prověření)“, mezi čarami „držet / sledovat“, pod
červenou „spíše nepřikupovat / zvážit prodej“ — čím dražší vůči vlastní historii, tím vyšší růst musí cenu
ospravedlnit. Zóna je i ve sloupci tabulky. Orientační pravidlo, zatím neověřené historickou výnosností.""",
    "/discovery": """Discovery — screener krátkodobého momenta u malých a středních firem (do ~50 mld. $):
hledá čerstvé momentum, neobvyklý objem a blízkost 52týdenního maxima. Discovery skóre 0–100 je heuristika, ne
predikce — hlavní hodnota jsou „důkazy“ pod ním (momentum 5d/20d, relativní objem, vzdálenost od 52w high, poloha
vůči SMA20/50, blížící se výsledky hospodaření). Rozcestník pro další zkoumání, ne doporučení k nákupu.""",
    "/smart-money": """Smart Money — nákupy a prodeje insiderů (vedení, ředitelé, >10% vlastníci) z hlášení
SEC Form 4: kdo, role, nákup (P) / prodej (S), hodnota obchodu. Nákupy mají obvykle větší vypovídací hodnotu než
prodeje (insideři prodávají z mnoha důvodů). Záložka Fondy: co drží, kupují a prodávají vybrané fondy
(Berkshire, Pershing Square, Appaloosa, Druckenmiller, aktivisté, tech fondy…) podle čtvrtletních výpisů SEC 13F —
nové pozice, navýšení, snížení, prodeje a konsenzus (kolik fondů tutéž akcii kupuje). 13F vychází až do 45 dnů
po konci čtvrtletí a neobsahuje shorty. Čerstvější jsou hlášení 13D/13G: fond překročil 5 % podílu ve firmě
(13D = aktivní záměr), podává se do 10 dnů.""",
    "/dark-pool": """Dark Pool — objemy obchodované mimo burzy (ATS/„dark pools“) z veřejných dat FINRA,
týdenně, s přibližně měsíčním zpožděním publikace; žebříček podle objemu v dolarech. Ukazuje, kde se obchoduje
velký objem mimo burzu — neříká směr (nákup vs prodej).""",
    "/legenda": """Legenda — vysvětlivky všech pojmů, zkratek a vzorců v aplikaci (78 pojmů, filtr podle modulu).""",
    "/predplatne": """Přístup — celý Tradezer je teď zdarma pro registrované (bez předplatného a bez karty). Funkce Elite (živá data, analytici) připravujeme — chybí licence dat, zatím nejdou koupit.""",
    "/admin": """Administrace — přehled uživatelů a provozu, jen pro správce Tradezeru.""",
    "/ucet": """Účet — nastavení účtu, export a smazání osobních údajů (GDPR), přístup (vše zdarma).""",
}


def page_key(path: str) -> str:
    seg = "/" + (path or "/").strip("/").split("/")[0]
    return seg if seg in PAGES else "/dashboard" if seg == "/" else seg


def page_description(path: str) -> str | None:
    return PAGES.get(page_key(path))
