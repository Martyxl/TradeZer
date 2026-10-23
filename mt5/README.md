# Tradezer Bias EA (MT5 / FTMO)

Osobní robot pro MetaTrader 5. **Zatím ve stavu „připraveno k ladění“** — výchozí `InpDryRun = true`
(jen loguje, neobchoduje). Na skutečné obchodování přepnout až po forward testu na demo / FTMO Free Trial.

## Strategie (stejná jako „živé výsledky entry plánu“ ve Statistikách)
1. Směr dne = denní bias Tradezeru (snapshot po London open 07:00 UTC).
2. Po NY open (13:30 UTC, do 15 min) limit **proti** biasu s offsetem (`offset_pct` z API).
3. SL = offset × `InpStopMult` za vstupem, bez TP; nevyplněný limit zrušit v 19:00 UTC, pozice zavřít v 20:50 UTC.
4. Velikost pozice z rizika `InpRiskPct` % zůstatku při zásahu SL.

Poctivá forward simulace (8 týdnů, 10/2026) **žádnou výhodu neukázala** — robot slouží k forward testu
na demu, ne k obchodování s penězi.

## FTMO pravidla, která robot hlídá
- **Zprávy:** ±`InpNewsBufferMin` (3) min kolem high-impact zpráv dané měny nesmí být aktivní limit
  (vyplnění = provedení). Robot limit stáhne a po zprávě obnoví. Seznam zpráv dodává API (kalendář
  ForexFactory). Platí na Standard FTMO Account (ne Free Trial / Challenge / Swing), robot to dělá vždy.
  Pozor: zásah SL během zprávy robot zabránit neumí.
- **Přestávky:** pozice se zavírají před 21:00 UTC (denní pauza), přes víkend nic nedrží.
- **Denní ztráta:** `InpDailyLossStopPct` (2 %) → zavře vše a do dalšího dne nic. FTMO limit je 5 % (2-Step)
  / 3 % (1-Step) a počítá se od půlnoci CE(S)T; robot počítá od půlnoci UTC (konzervativně níž).
- Kalendář nedostupný (`news_ok=0`) → ten den neobchoduje (`InpTradeWithoutNews = false`).

## Instalace
1. Soubor `Tradezer_BiasEA.mq5` do `MQL5/Experts/Tradezer/` terminálu (FTMO MT5: Soubor → Otevřít složku dat)
   a zkompilovat v MetaEditoru (F7). *(Zkompilováno a nahráno do lokálního FTMO MT5 23. 10. 2026.)*
2. **Nástroje → Možnosti → Poradci:** zaškrtnout „Povolit WebRequest pro uvedené URL“ a přidat
   `https://tradezer.app`. Bez toho robot plán nestáhne (v deníku „HTTP -1 … chyba 4014“).
3. Přetáhnout EA na libovolný graf (stačí jeden; obchoduje všechny symboly z `InpTickers`), povolit Algo Trading.
4. Zkontrolovat názvy symbolů v Market Watch. Ověřené na FTMO: `US100.cash`, `US30.cash`, `US500.cash`,
   `XAUUSD`. Forex páry přidat do `InpTickers` až po ověření názvů (např. `EURUSD=EURUSD`).

## Log
- Záložka Experti v terminálu + soubor `MQL5/Files/tradezer_ea_log.csv` (každý krok: plán, limit, zrušení,
  zavření s P/L, chyby).

## API
`GET https://tradezer.app/api/ea/plan?ticker=NQ` → text `klíč=hodnota`
(`date, direction, trust, offset_pct, ny_open_utc, close_utc, news_ok, news=čas|měna|název`).

## Omezení / TODO při ladění
- Strategy Tester nepodporuje WebRequest → jen forward test na demu.
- Čas = `TimeGMT()` (hodiny PC musí být správně).
- Hlášení skutečných obchodů zpět do Tradezeru (pro Statistiky z reálných fillů) zatím není.
