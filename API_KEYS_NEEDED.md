# API klíče potřebné pro Tradezer

## Povinné

### 1. Anthropic Claude API
- **Proč:** LLM klasifikace zpráv + denní doporučení
- **Kde:** https://console.anthropic.com/
- **Free tier:** 5 USD credit pro nové účty, pak pay-as-you-go
- **Cena:** ~$0.003/1K tokenů (Sonnet) — odhad pro 200 zpráv/den: ~$0.05/den
- **Env var:** `ANTHROPIC_API_KEY`

---

## Volitelné (aplikace funguje i bez nich, ale s méně zdroji)

### 2. NewsAPI
- **Proč:** Agregace anglických finančních zpráv (Reuters, Bloomberg, CNBC...)
- **Kde:** https://newsapi.org/register
- **Free tier:** 100 requestů/den, jen 1 měsíc starý obsah
- **Developer plan:** $449/měsíc (nebo hledej student/academic plan)
- **Alternativa zdarma:** RSS adaptéry pokrývají část obsahu
- **Env var:** `NEWSAPI_KEY`

### 3. Finnhub
- **Proč:** Forex zprávy + company news pro centrální banky
- **Kde:** https://finnhub.io/register
- **Free tier:** 60 API calls/minuta — dostačující pro náš use case
- **Env var:** `FINNHUB_API_KEY`

### 4. Alpha Vantage
- **Proč:** NEWS_SENTIMENT endpoint s vestavěným topic taggingem
- **Kde:** https://www.alphavantage.co/support/#api-key
- **Free tier:** 25 requestů/den (velmi limitované), 500/den za $50/měsíc
- **Env var:** `ALPHAVANTAGE_API_KEY`

---

## Zdroje ZDARMA (bez klíče)

### Forex Factory XML
- Ekonomický kalendář s impact ratingem a actual/forecast hodnotami
- URL: `https://www.forexfactory.com/ff_calendar_thisweek.xml`
- **Nejcennější zdroj pro EUR/USD** — žádný klíč nepotřeba

### RSS feeds
- Reuters Business: `https://feeds.reuters.com/reuters/businessNews`
- ECB Press: `https://www.ecb.europa.eu/rss/press.html`

### Yahoo Finance (yfinance)
- Historická OHLCV data pro kalibraci
- Bezplatné, bez klíče, ale throttlované

---

## Doporučené pořadí pro první spuštění

1. Nastav `ANTHROPIC_API_KEY` (povinné pro LLM predikce)
2. Aplikace funguje hned s Forex Factory + RSS zdroji
3. Přidej `FINNHUB_API_KEY` pro více zpráv (free tier stačí)
4. `NEWSAPI_KEY` a `ALPHAVANTAGE_API_KEY` přidej až když budeš chtít škálovat

---

## Nastavení .env

```bash
cp .env.example .env
# Edituj .env a doplň klíče
```
