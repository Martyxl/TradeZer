# Tradezer — Nasazení na Vercel (krok za krokem)

Projekt se skládá ze dvou částí:
- **`api/`** — FastAPI backend (Python) → Vercel Serverless Functions
- **`web/`** — Next.js frontend → Vercel Static + Edge

Každá část se nasazuje jako **samostatný Vercel projekt**.

---

## Krok 1 — Databáze (PostgreSQL)

SQLite nefunguje na Vercelu. Potřebuješ cloudovou PostgreSQL databázi.

### Doporučeno: Neon (zdarma)

1. Jdi na **[neon.tech](https://neon.tech)** → Sign up (GitHub účet stačí)
2. Create Project → zadej název (např. `tradezer`)
3. Po vytvoření zkopíruj **Connection string** ve formátu:
   ```
   postgresql://user:password@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require
   ```
4. Tenhle connection string budeš potřebovat v dalším kroku.

> Alternativy: **Supabase** (supabase.com) nebo **Vercel Postgres** (v Vercel dashboardu).

---

## Krok 2 — Deploy API (`api/` složka)

### 2a. Import projektu na Vercel

1. Jdi na **[vercel.com](https://vercel.com)** → Log in → **Add New Project**
2. Import Git Repository → vyber repozitář `TradeZer`
3. **Důležité:** Nastav **Root Directory** na `api`
4. Framework Preset: nechej **Other**
5. Klikni na **Environment Variables** a přidej tyhle proměnné:

| Key | Value |
|-----|-------|
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` (tvůj klíč) |
| `DATABASE_URL` | connection string z Neon (krok 1) |
| `APP_ENV` | `production` |
| `INTERNAL_API_TOKEN` | vymysli silné heslo, např. `muj-tajny-token-2026` |

6. Klikni **Deploy** a počkej na build (cca 1–2 minuty)
7. Po deployi dostaneš URL ve tvaru `tradezer-api.vercel.app` — **zkopíruj si ji**

### 2b. Inicializace databáze

Po prvním deployi musíš jednorázově spustit seed (vytvoří tabulky a základní data):

```bash
curl -X POST https://tradezer-api.vercel.app/api/refresh \
  -H "X-Internal-Token: muj-tajny-token-2026"
```

> Tenhle příkaz:
> - Vytvoří všechny tabulky v PostgreSQL databázi (automaticky při startu)
> - Stáhne zprávy ze všech RSS zdrojů (ECB, FXStreet, Mining.com, CNBC...)
> - Spustí LLM klasifikaci pro každou zprávu (~5–10 minut kvůli počtu LLM volání)

Pokud chceš seed dat (tickery, zdroje, kategorie) spustit samostatně, použij:
```bash
curl https://tradezer-api.vercel.app/
# Tabulky se vytvoří automaticky při prvním requestu
```

Pak spusť refresh výše.

---

## Krok 3 — Deploy Web (`web/` složka)

### 3a. Import projektu na Vercel

1. **Add New Project** (znovu, nový projekt)
2. Import stejný repozitář `TradeZer`
3. **Důležité:** Nastav **Root Directory** na `web`
4. Framework Preset: **Next.js** (Vercel to detekuje automaticky)
5. **Environment Variables:**

| Key | Value |
|-----|-------|
| `NEXT_PUBLIC_API_URL` | URL z kroku 2 (např. `https://tradezer-api.vercel.app`) |

6. Klikni **Deploy**
7. Frontend bude dostupný na `tradezer.vercel.app` (nebo vlastní doméně)

---

## Krok 4 — Automatický refresh zpráv

APScheduler nefunguje na Vercel serverless. Refresh musíš spouštět externě.

### Možnost A: Vercel Cron Jobs (Pro plán)

V `api/` projektu → Settings → Cron Jobs → Add Cron Job:
```
Schedule:  */15 * * * *
Path:      /api/refresh
Method:    POST
Headers:   X-Internal-Token: muj-tajny-token-2026
```
Tím se zprávy aktualizují každých 15 minut.

### Možnost B: cron-job.org (zdarma)

1. Jdi na **[cron-job.org](https://cron-job.org)** → Sign up → New cronjob
2. URL: `https://tradezer-api.vercel.app/api/refresh`
3. Metoda: POST
4. Header: `X-Internal-Token: muj-tajny-token-2026`
5. Schedule: každých 15 minut

---

## Krok 5 — Vlastní doména (volitelné)

### Pro frontend:
Vercel projekt (web) → Settings → Domains → Add Domain → `tradezer.cz`

### CORS pro vlastní doménu:
Přidej do API projektu na Vercelu environment variable:
```
ALLOWED_ORIGIN=https://tradezer.cz
```

---

## Přehled environment variables

### API projekt (`api/`)

| Proměnná | Povinná | Popis |
|----------|---------|-------|
| `ANTHROPIC_API_KEY` | ✅ | LLM klasifikace zpráv |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `APP_ENV` | ✅ | Nastav na `production` |
| `INTERNAL_API_TOKEN` | ✅ | Ochrana `/api/refresh` endpointu |
| `ALLOWED_ORIGIN` | ❌ | Vlastní doména pro CORS (např. `https://tradezer.cz`) |
| `NEWSAPI_KEY` | ❌ | Více zdrojů zpráv (volitelné) |
| `FINNHUB_API_KEY` | ❌ | Více zdrojů zpráv (volitelné) |

### Web projekt (`web/`)

| Proměnná | Povinná | Popis |
|----------|---------|-------|
| `NEXT_PUBLIC_API_URL` | ✅ | URL nasazeného API (bez trailing slash) |

---

## Ověření funkčnosti

Po nasazení zkontroluj:

```bash
# API zdraví
curl https://tradezer-api.vercel.app/

# Zprávy pro EUR/USD
curl https://tradezer-api.vercel.app/api/news?ticker=EURUSD&limit=3

# Frontend
# Otevři https://tradezer.vercel.app v prohlížeči
```

---

## Lokální vývoj (reference)

```bash
# Spuštění backendu
cd api
pip install -r requirements.txt
python -m app.db.seed
uvicorn app.main:app --reload --port 8000

# Spuštění frontendu
cd web
npm install
npm run dev   # → http://localhost:3000
```
