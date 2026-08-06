# META PROMPT — Tradezer Valuation Radar

> Vlož celý tento soubor jako první zprávu do Claude Code (nebo ulož jako `docs/VALUATION_MODULE.md` a odkaž na něj).
> Cíl: nový modul do tradezer.app, který sbírá fundamenty firem, deterministicky skóruje, jestli je valuace zdravá nebo přepálená, a zobrazuje to jako bublinovou mapu po skupinách.

---

## 0. Role a způsob práce

Jsi senior backend + data engineer. Stavíš produkční modul do existující aplikace **tradezer.app**.

**Než napíšeš první řádek kódu:**
1. Prozkoumej repozitář a napiš mi shrnutí: jaký je stack (framework, ORM, migrace, task runner, frontend), kde jsou existující moduly, jaká je konvence pro API routy, testy a konfiguraci.
2. Navrhni, kam přesně modul zasadit, aby respektoval stávající strukturu. **Nezakládej paralelní architekturu.**
3. Vypiš seznam otevřených otázek, kde ti spec nestačí.
4. **Počkej na moje potvrzení.** Pak teprve začni fází P0.

Po každé fázi: zastav se, ukaž diff a shrnutí, počkej na schválení. Nesnaž se udělat všechno v jednom průchodu.

---

## 1. Co modul dělá (produktový popis)

Uživatel otevře stránku „Valuation Radar“. Vidí bublinovou mapu firem:

- **osa X** = jak je akcie drahá vůči vlastní 5leté historii (percentil forward P/E, 0–100)
- **osa Y** = očekávaný růst EPS na příštích 12 měsíců (%)
- **velikost bubliny** = tržní kapitalizace
- **barva** = verdikt valuace (levná / férová / napjatá / přepálená)
- **filtr / seskupení** = sektorová skupina (tech, farmacie, komodity, potraviny, nemovitosti…)

Kliknutím na bublinu se otevře detail karta:
- poslední reportované výsledky (tržby, EPS, marže, FCF) + YoY
- co se čeká příští kvartál a příští rok (konsenzus, počet analytiků, rozptyl low/high)
- jak se odhady posunuly za 30 a 90 dní (revize nahoru/dolů)
- historie překvapení (beat/miss) za poslední 4 kvartály
- rozpad skóre na komponenty s vysvětlením, co skóre táhne nahoru a dolů
- verdikt vhodnosti pro držbu 1 měsíc a déle
- **confidence** (jak moc jsou data kompletní)

Nejde o signál k obchodu. Je to filtr pro delší horizont, oddělený od intradenní části aplikace.

---

## 2. TVRDÁ OMEZENÍ (nedodržení = chyba, ne preference)

1. **Veškerá čísla, metriky a skóre jsou deterministické a čistě spočítané v kódu.** LLM nikdy nepočítá, nedopočítává chybějící hodnotu, neodhaduje. LLM smí jen napsat textové shrnutí *nad již spočítanými čísly*, která dostane na vstupu.
2. **Point-in-time data.** Snapshoty se nikdy nepřepisují. Každý fetch = nový append-only řádek s `as_of_date` a `ingested_at`. Revize výkazů se ukládají jako nová verze, ne jako update. Bez tohohle nikdy nezpětně neověříš, jestli skóre fungovalo.
3. **Žádný look-ahead bias.** Metrika k datu `D` smí použít jen data, která byla k dispozici k datu `D` (tzn. výkaz až po `report_date`, ne po `period_end`).
4. **Žádné volání externího API z request pathu.** Ingest běží jako naplánovaný job. API čte jen z DB.
5. **Chybějící data se nedopočítávají ani neimputují.** Chybí → `NULL`, komponenta se ze skóre vyřadí, váhy se přenormalizují a **confidence klesne**. Nikdy neukazuj plné skóre nad děravými daty.
6. **Klíče jen z `.env`.** Žádný klíč, ticker ani URL natvrdo v kódu. Poskytovatel dat je volitelný přes `.env` (viz sekce 4).
7. **Verzování modelu.** Každý řádek skóre nese `model_version`. Změna vah nebo vzorce = inkrement verze, stará skóre se nepřepočítávají zpětně.
8. **Disclaimer je součást API response i UI**, ne poznámka pod čarou. Modul dělá heuristickou analýzu z veřejných dat, není to investiční doporučení.

---

## 3. Univerzum tickerů

**Dvě oddělené množiny — tohle je zásadní, nespleť je:**

- `DISPLAY_UNIVERSE` — 10 největších firem z NASDAQ-100, které se zobrazují. Startovní sada (ověř aktuální váhy při běhu, mění se): `NVDA, MSFT, AAPL, AMZN, AVGO, META, GOOGL, TSLA, NFLX, COST`.
- `PEER_UNIVERSE` — širší množina (~150–200 tickerů) používaná **výhradně pro výpočet sektorových statistik** (medián, z-score). Doporučení: celý NDX100 + top holdings sektorových ETF `XLV, XLE, XLP, XLRE, XLF, XLI, XLU`.

**Proč:** top 10 NDX je téměř výhradně tech. Kdybys počítal sektorové z-score jen z těch deseti, „relativně levný tech“ by znamenal jen „levnější než NVDA“ — statisticky bezcenné. Peer statistiky musí stát na širokém vzorku. Obě množiny konfigurovatelné v `.env` / seed souboru, ne v kódu.

---

## 4. Datové zdroje (adapter pattern)

Definuj rozhraní `MarketDataProvider` s metodami:

```
get_profile(ticker) -> Profile            # název, burza, GICS sektor/industry, měna, shares outstanding
get_financials(ticker) -> list[Statement] # quarterly + annual, min. 5 let zpět
get_estimates(ticker) -> Estimates        # EPS a revenue: aktuální Q, příští Q, FY0, FY1 + low/high/n_analysts
get_revisions(ticker) -> Revisions        # posun konsenzu za 7/30/60/90 dní, počet up/down revizí
get_earnings_history(ticker) -> list      # actual vs estimate za posledních 8 kvartálů + report_date
get_prices(ticker, from, to) -> DataFrame # denní OHLCV adjusted
```

**Implementace:**

- **`YFinanceProvider` (primární, default).** Používá `yfinance.Ticker`: `income_stmt`, `quarterly_income_stmt`, `balance_sheet`, `cashflow`, `earnings_estimate`, `revenue_estimate`, `growth_estimates`, `eps_trend`, `eps_revisions`, `earnings_history`, `earnings_dates`, `analyst_price_targets`, `info`, `history()`.
- **`FMPProvider` (volitelný fallback).** Free tier = 250 req/den, jen `stable` endpointy; legacy endpointy pro nové účty nefungují, earnings calendar a stock peers jsou placené. Neplánuj na nich závislost.
- **`FixtureProvider` (povinný).** Čte zmrazené JSON fixtures z disku. Používá se ve všech testech. Testy **nikdy** nesmí síťovat.

Výběr přes `.env`: `MARKET_DATA_PROVIDER=yfinance`.

**Provozní pravidla ingestu:**
- Rate limiting a exponenciální backoff, sekvenčně, ne paralelně přes všechny tickery.
- Lokální cache surových odpovědí na disk/DB s TTL z `.env` — během vývoje nechceš tahat stejná data pořád dokola.
- Ingest je **idempotentní**: opakovaný běh za stejný den nezaloží duplicity (unique constraint, ne aplikační kontrola).
- Loguj per-ticker success/fail; jeden padlý ticker nesmí shodit celý běh.

**⚠️ Licenční poznámka, kterou mi explicitně připomeň v shrnutí P1:** yfinance je neoficiální scraper Yahoo Finance a Yahoo svá data označuje jako informativní, nikoli pro obchodní/investiční účely. Pro vývoj a osobní použití OK. Ve chvíli, kdy tradezer.app bude komerční produkt s placenými uživateli, je potřeba licencovaný feed (FMP placený plán, EODHD, Finnhub, Polygon). Architektura přes `MarketDataProvider` musí tuhle výměnu udělat záležitostí jedné třídy.

---

## 5. Datový model (PostgreSQL)

Vytvoř migrace. Tabulky, minimální sloupce:

**`val_instruments`** — `ticker` (PK), `name`, `exchange`, `currency`, `gics_sector`, `gics_industry`, `group_key` (FK), `in_display_universe` (bool), `in_peer_universe` (bool), `active`, `updated_at`

**`val_groups`** — `key` (PK), `label_cs`, `label_en`, `color_hex`, `sort_order`, `description`

**`val_raw_snapshots`** — `id`, `ticker`, `source`, `endpoint`, `as_of_date`, `payload` (JSONB), `ingested_at`. Append-only, nikdy UPDATE ani DELETE. Unique: `(ticker, source, endpoint, as_of_date)`

**`val_financials`** — `ticker`, `period_end`, `period_type` (Q/FY), `report_date`, `revenue`, `gross_profit`, `operating_income`, `ebitda`, `net_income`, `eps_diluted`, `shares_diluted`, `cfo`, `capex`, `total_debt`, `cash_and_equivalents`, `total_equity`, `source`, `revision_no`, `ingested_at`. Unique: `(ticker, period_end, period_type, revision_no)`

**`val_estimates`** — `ticker`, `as_of_date`, `horizon` (`current_q`/`next_q`/`current_y`/`next_y`), `metric` (`eps`/`revenue`), `avg`, `low`, `high`, `n_analysts`, `year_ago_value`, `source`. Unique: `(ticker, as_of_date, horizon, metric)`

**`val_estimate_trend`** — `ticker`, `as_of_date`, `horizon`, `current`, `days_ago_7`, `days_ago_30`, `days_ago_60`, `days_ago_90`, `up_last_30d`, `down_last_30d`

**`val_earnings_history`** — `ticker`, `period_end`, `report_date`, `eps_actual`, `eps_estimate`, `surprise_pct`

**`val_prices_daily`** — `ticker`, `date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`. Unique: `(ticker, date)`

**`val_metrics_daily`** — `ticker`, `as_of_date`, všechny spočítané metriky ze sekce 6, `model_version`. Unique: `(ticker, as_of_date, model_version)`

**`val_scores_daily`** — `ticker`, `as_of_date`, `valuation_score`, `growth_score`, `quality_score`, `revision_score`, `trend_score`, `composite_score`, `valuation_verdict`, `horizon_verdict`, `bubble_flag` (bool), `confidence` (0–1), `drivers` (JSONB — top 3 pozitivní a top 3 negativní faktory s hodnotami), `model_version`. Unique: `(ticker, as_of_date, model_version)`

**`val_score_runs`** — audit: `id`, `started_at`, `finished_at`, `model_version`, `tickers_ok`, `tickers_failed`, `notes`

Indexy na `(ticker, as_of_date DESC)` všude, kde se čte poslední hodnota.

---

## 6. Metriky (přesné definice — implementuj jako čisté funkce, každou samostatně testovanou)

Vše TTM = součet posledních 4 kvartálů. Fallback na roční data pokud kvartály chybí, s poznámkou v `drivers`.

**Základ**
```
market_cap        = close * shares_diluted
net_debt          = total_debt - cash_and_equivalents
enterprise_value  = market_cap + net_debt
fcf_ttm           = cfo_ttm - abs(capex_ttm)
```

**Násobky**
```
pe_ttm       = close / eps_diluted_ttm                (NULL pokud eps <= 0)
pe_fwd       = close / eps_ntm                        (eps_ntm = vážený mix current_y a next_y podle
                                                       zbývajících měsíců do konce fiskálního roku)
ev_ebitda    = enterprise_value / ebitda_ttm          (NULL pokud ebitda <= 0)
ev_sales     = enterprise_value / revenue_ttm
p_fcf        = market_cap / fcf_ttm                   (NULL pokud fcf <= 0)
peg_fwd      = pe_fwd / (eps_growth_ntm_pct)          (NULL pokud růst <= 0)
```

**Percentily vůči vlastní historii** — pro každý násobek spočítej rolling řadu za posledních 5 let (denní cena × tehdejší TTM/fwd zisk) a urči, v jakém percentilu je dnešní hodnota. `pctile_pe_fwd = 95` znamená „dražší než v 95 % vlastní historie“.

**Peer z-score** — v rámci `group_key` nad `PEER_UNIVERSE`: `z = (hodnota − medián_skupiny) / MAD_skupiny`. Používej medián a MAD, ne průměr a směrodatnou odchylku — jinak ti jedna extrémní firma rozhodí celou skupinu. Winsorizuj na ±3.

**Růst**
```
revenue_yoy_ttm, eps_yoy_ttm
revenue_growth_ntm  = z konsenzu revenue
eps_growth_ntm      = z konsenzu EPS
growth_accel        = eps_growth_ntm − eps_yoy_ttm    (kladné = zrychlení)
```

**Kvalita**
```
gross_margin, operating_margin, fcf_margin = fcf_ttm / revenue_ttm
roic                = nopat_ttm / (total_debt + total_equity − cash)   ; nopat = op_income * (1 − 0.21)
net_debt_to_ebitda  = net_debt / ebitda_ttm
margin_trend        = operating_margin_ttm − operating_margin_ttm_rok_zpět
share_count_change  = YoY změna shares_diluted        (záporné = buybacky)
```

**Momentum odhadů**
```
revision_ratio_30d = (up_30d − down_30d) / max(up_30d + down_30d, 1)      → −1..1
estimate_drift_90d = (current − days_ago_90) / abs(days_ago_90)
avg_surprise_4q    = průměr surprise_pct za poslední 4 kvartály
```

**Trend a riziko**
```
px_vs_sma200 = close / SMA200 − 1
mom_12_1     = výnos za 12 měsíců bez posledního měsíce
max_dd_1y, realized_vol_60d
```

---

## 7. Skórovací engine

Čistý, izolovaný modul bez I/O. Vstup = dataclass metrik, výstup = dataclass skóre. Žádný přístup do DB uvnitř.

### Normalizace
Každá metrika → subskóre 0–100 přes explicitní mapovací funkci (buď percentil v peer skupině, nebo po částech lineární škála s definovanými prahy). **Prahy definuj v jednom konfiguračním souboru `scoring_config.py`, ne roztroušené v kódu.**

### Komponenty a váhy

**Valuation score (jak je to drahé — vyšší = levnější)**
| Vstup | Váha |
|---|---|
| `pctile_pe_fwd` (invertovaný) | 35 % |
| `pctile_ev_ebitda` (invertovaný) | 25 % |
| peer z-score `pe_fwd` (invertovaný) | 20 % |
| `peg_fwd` band (<1 = 100, 1–1.5 = 75, 1.5–2 = 50, 2–3 = 25, >3 = 0) | 20 % |

**Growth score:** `eps_growth_ntm` 40 %, `revenue_growth_ntm` 30 %, `revenue_yoy_ttm` 20 %, `growth_accel` 10 %

**Quality score:** `roic` 30 %, `fcf_margin` 25 %, `net_debt_to_ebitda` (invertovaný) 20 %, `margin_trend` 15 %, `share_count_change` (invertovaný) 10 %

**Revision score:** `revision_ratio_30d` 45 %, `estimate_drift_90d` 35 %, `avg_surprise_4q` 20 %

**Trend score:** `px_vs_sma200` 50 %, `mom_12_1` 30 %, `max_dd_1y` (invertovaný) 20 %

### Verdikty

**Valuace** — čistě z `valuation_score`:
```
>= 70  LEVNÁ        zelená
55–70  FÉROVÁ       světle zelená
40–55  NAPJATÁ      oranžová
<  40  PŘEPÁLENÁ    červená
```

**`bubble_flag`** = True když platí **současně**:
`pctile_pe_fwd > 85` **AND** `growth_accel < 0` **AND** `revision_ratio_30d < 0`

Tj. drahé vůči vlastní historii, růst zpomaluje a analytici sekají odhady. Drahá akcie se zrychlujícím růstem a rostoucími odhady bublina není — a tenhle rozdíl je celý smysl modulu. Nedávej flag jen podle vysokého P/E.

**Composite (vhodnost na 1M+)**
```
composite = 0.35*valuation + 0.25*growth + 0.20*quality + 0.15*revision + 0.05*trend
```
```
>= 70  VHODNÁ K DRŽBĚ
55–70  SPÍŠE ANO
40–55  NEUTRÁLNÍ
<  40  SPÍŠE NE
```

### Confidence (0–1)
Násobek tří faktorů: podíl vyplněných vstupních metrik × pokrytí analytiky (`min(n_analysts/15, 1)`) × délka dostupné historie (`min(roky/5, 1)`).
**Pokud `confidence < 0.5`, API i UI musí verdikt označit jako nespolehlivý a vizuálně ztlumit.**

### `drivers`
Vždy vrať top 3 faktory táhnoucí skóre nahoru a top 3 dolů, s názvem, hodnotou a příspěvkem v bodech. Uživatel musí vidět **proč**, ne jen číslo.

---

## 8. Skupiny

Seed `val_groups`, mapování z GICS sektoru + explicitní override tabulka pro výjimky:

| key | label_cs |
|---|---|
| `tech` | Technologie a software |
| `semis` | Polovodiče |
| `comms` | Média a komunikace |
| `healthcare` | Farmacie a zdravotnictví |
| `finance` | Finance a banky |
| `staples` | Potraviny a spotřební zboží |
| `discretionary` | Zbytné zboží a retail |
| `energy` | Energetika |
| `materials` | Komodity a materiály |
| `realestate` | Nemovitosti |
| `utilities` | Utility |
| `industrials` | Průmysl |

Polovodiče odděl od techu záměrně — mají zásadně jinou cykličnost i násobky, míchat NVDA s MSFT do jedné peer skupiny zkresluje z-score.

---

## 9. API

Respektuj stávající konvence repa. Endpointy:

```
GET  /api/v1/valuation/groups
GET  /api/v1/valuation/overview?group=tech&min_confidence=0.5
GET  /api/v1/valuation/{ticker}
GET  /api/v1/valuation/{ticker}/history?days=365
POST /api/v1/valuation/refresh          # admin, spustí ingest+scoring, vrací run_id
GET  /api/v1/valuation/runs/{run_id}
```

Každá response nese `as_of_date`, `model_version`, `data_source` a `disclaimer`. Pydantic (nebo ekvivalent) schémata pro vše, žádné volné dicty.

---

## 10. Frontend

Drž se existujícího design systému a komponent v repu.

**Bubble mapa** — scatter, X = `pctile_pe_fwd`, Y = `eps_growth_ntm`, velikost = market cap (sqrt škála), barva = verdikt. Svislá referenční čára na percentilu 50, vodorovná na 0 % růstu → čtyři kvadranty s popisky: *levné a rostoucí* / *drahé a rostoucí* / *levné a zpomalující* / *drahé a zpomalující*. Filtr skupin jako chipy. Přepínač zobrazení: bublinová mapa ↔ tabulka.

**Detail karta** — sekce: Poslední výsledky | Očekávání | Revize odhadů | Rozpad skóre (horizontální bar chart komponent) | Verdikt + confidence badge. Historie překvapení jako malý sparkline.

Bubble flag = výrazný vizuální marker (např. červený obrys s ikonou), ne jen odstín barvy.

Prázdné a chybové stavy řeš explicitně: chybí data → text „Nedostatek dat pro hodnocení“, ne prázdný graf.

---

## 11. LLM shrnutí (až úplně nakonec, fáze P6)

Samostatný endpoint `GET /api/v1/valuation/{ticker}/summary`, cache na 24 h v DB.

- Model konfigurovatelný přes `.env` (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`) — musí fungovat proti LiteLLM i proti Claude API bez změny kódu.
- `temperature=0.2`.
- Prompt dostane **jen už spočítaná čísla** ve strukturovaném JSON. Instrukce: shrň česky do 3 odrážek, max 40 slov každá; používej výhradně dodaná čísla; pokud údaj chybí, napiš že chybí; nikdy nedoporučuj nákup ani prodej.
- Odpověď se ukládá s hashem vstupu — když se čísla nezměnila, negeneruj znovu.
- Když LLM selže, endpoint vrací prázdné shrnutí. **Zbytek modulu na LLM nesmí být závislý.**

---

## 12. Testy

- **Golden fixtures:** zmraz reálné JSON odpovědi pro 3 tickery (NVDA, COST, a jeden s chybějícími daty) do `tests/fixtures/`. Snapshot test celého skóre.
- **Property testy:** skóre vždy v 0–100; při jinak konstantních vstupech vyšší `pe_fwd` → nižší `valuation_score` (monotonie); chybějící vstup → nižší confidence, nikdy exception.
- **Edge cases:** záporný EPS, záporná EBITDA, nulové FCF, nula analytiků, ticker s historií kratší než 5 let, split akcií uprostřed řady.
- **Idempotence ingestu:** dvojí běh za stejný den → stejný počet řádků.
- **Bez sítě:** celá test suite běží offline přes `FixtureProvider`.

**Acceptance kritéria pro dokončení:**
1. `make ingest && make score` naplní DB pro celé `PEER_UNIVERSE` bez chyby.
2. `/api/v1/valuation/overview` vrací 10 firem s neprázdnými skóre a confidence.
3. UI vykreslí bublinovou mapu s funkčním filtrem skupin a detail kartou.
4. Test suite zelená, běží offline, coverage skórovacího modulu ≥ 90 %.
5. Opakovaný ingest nevytvoří duplicity.

---

## 13. Fáze

| Fáze | Obsah | Výstup |
|---|---|---|
| **P0** | Průzkum repa, návrh umístění, migrace, seed skupin a univerza | Schéma + seed |
| **P1** | `MarketDataProvider`, `YFinanceProvider`, `FixtureProvider`, ingest job, cache | Naplněné raw + normalizované tabulky |
| **P2** | Výpočet metrik, historické percentily, peer z-scores | `val_metrics_daily` |
| **P3** | Skórovací engine + `scoring_config.py` + kompletní testy | `val_scores_daily` |
| **P4** | API vrstva + schémata | Funkční endpointy |
| **P5** | Frontend: bublinová mapa + detail karta | Použitelné UI |
| **P6** | LLM shrnutí, scheduler, jednoduchý backtest skóre vs. 1M/3M forward return | Doplňky |

Stop po každé fázi.

---

## 14. Anti-patterny — čemu se vyhnout

- ❌ Volání yfinance z API handleru
- ❌ UPDATE nad snapshot tabulkami
- ❌ Peer statistiky počítané jen z 10 zobrazených firem
- ❌ Imputace chybějících hodnot průměrem nebo nulou
- ❌ LLM, který dopočítává nebo interpretuje surová data
- ❌ Magic numbers ve skórovací logice mimo `scoring_config.py`
- ❌ Průměr + std místo mediánu + MAD u peer srovnání
- ❌ Vlastní HTTP klient / ORM / config loader, když repo už nějaký má
- ❌ Testy sahající na síť
- ❌ Bubble flag jen z vysokého P/E bez podmínky na růst a revize

---

## 15. Poznámka k interpretaci

Skóre je heuristika nad veřejnými daty s nejistou kvalitou, ne ocenění firmy. Konsenzus analytiků je systematicky optimistický a u velkých tech firem bývá forward P/E ospravedlnitelné růstem, který se do jednoduchých násobků nevejde. Modul má sloužit jako **filtr a rozcestník k dalšímu zkoumání**, ne jako rozhodovací mechanismus. Tenhle rámec musí být zřejmý i z UI.
