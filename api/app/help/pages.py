"""Popisy stránek Tradezeru pro chatovacího pomocníka (co stránka ukazuje a jak ji číst).

Klíč = první segment cesty (např. "/discovery"). Doplňuje Legendu (glossary.json), která vysvětluje
jednotlivé pojmy a vzorce. Při přidání/změně stránky aktualizovat i tady.
"""

OVERVIEW = """Tradezer (tradezer.app) je česká aplikace pro tradery a investory. AI (jazykový model) čte ekonomické
zprávy a kalendář a odhaduje jejich dopad na trhy; k tomu nabízí screenery a nástroje pro investice.
Sledované trhy: NQ (Nasdaq 100 futures), ES (S&P 500), YM (Dow Jones), XAUUSD (zlato), EURUSD, GBPUSD, USDJPY.
Menu má skupiny Trading (Deník, Historie, ORB Radar, Statistiky) a Investice (Investice, Daně, TRADEZER investuje,
Valuation Radar, Discovery, Smart Money, Dark Pool). Některé moduly jsou v placených plánech (Trader, Pro).
Vše je edukativní analýza z veřejných dat — NENÍ to investiční doporučení."""

PAGES: dict[str, str] = {
    "/dashboard": """Dashboard — hlavní přehled pro zvolený instrument (přepínač tickerů nahoře).
- Zprávy: proud ekonomických zpráv a událostí z kalendáře; u každé AI odhad pravděpodobnosti pohybu instrumentu
  nahoru / do strany (neutral) / dolů v následujících ~30 minutách a důležitost zprávy. Reakce se měří od ceny těsně
  před zprávou; u vydaných makro dat (např. „194K vs 200K expected“) od plánovaného času vydání.
- BIAS: denní směrový náklon (LONG/SHORT/NEUTRAL) složený z predikcí zpráv obchodního dne; snapshot po London open
  (07:00 UTC). Pondělní bias zahrnuje i zprávy z víkendu. Trust score = důvěryhodnost (≥65 vysoká).
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
    "/stats": """Statistiky (plán Trader) — tržní statistiky z 5min dat: velikost session (Asia/London/NY), kde se tiskne
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
    "/valuation": """Valuation Radar (plán Trader) — fundamentální ocenění amerických akcií: bublinová mapa (osa X =
percentil forward P/E vůči vlastní historii firmy, osa Y = očekávaný růst zisku, velikost = tržní kapitalizace,
barva = verdikt). Překrývající se bubliny se slučují do kolečka s počtem — kliknutím se zobrazí seznam firem.
Skóre valuace, růstu, kvality, revizí, trendu a kompozitní skóre 0–100, verdikty LEVNÁ/FÉROVÁ/NAPJATÁ/PŘEPÁLENÁ a
bublinová vlajka. Firmu lze přidat polem nahoře (ticker nebo název).""",
    "/discovery": """Discovery (plán Pro) — screener krátkodobého momenta u malých a středních firem (do ~50 mld. $):
hledá čerstvé momentum, neobvyklý objem a blízkost 52týdenního maxima. Discovery skóre 0–100 je heuristika, ne
predikce — hlavní hodnota jsou „důkazy“ pod ním (momentum 5d/20d, relativní objem, vzdálenost od 52w high, poloha
vůči SMA20/50, blížící se výsledky hospodaření). Rozcestník pro další zkoumání, ne doporučení k nákupu.""",
    "/smart-money": """Smart Money (plán Pro) — nákupy a prodeje insiderů (vedení, ředitelé, >10% vlastníci) z hlášení
SEC Form 4: kdo, role, nákup (P) / prodej (S), hodnota obchodu. Nákupy mají obvykle větší vypovídací hodnotu než
prodeje (insideři prodávají z mnoha důvodů).""",
    "/dark-pool": """Dark Pool (plán Pro) — objemy obchodované mimo burzy (ATS/„dark pools“) z veřejných dat FINRA,
týdenně, s přibližně měsíčním zpožděním publikace; žebříček podle objemu v dolarech. Ukazuje, kde se obchoduje
velký objem mimo burzu — neříká směr (nákup vs prodej).""",
    "/legenda": """Legenda — vysvětlivky všech pojmů, zkratek a vzorců v aplikaci (78 pojmů, filtr podle modulu).""",
    "/predplatne": """Předplatné — plány Free, Trader, Pro (Elite) a co odemykají; platby přes Stripe.""",
    "/ucet": """Účet — nastavení účtu, export a smazání osobních údajů (GDPR), přehled předplatného.""",
}


def page_key(path: str) -> str:
    seg = "/" + (path or "/").strip("/").split("/")[0]
    return seg if seg in PAGES else "/dashboard" if seg == "/" else seg


def page_description(path: str) -> str | None:
    return PAGES.get(page_key(path))
