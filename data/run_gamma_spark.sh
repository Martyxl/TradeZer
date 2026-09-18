#!/usr/bin/env bash
# Gamma (GEX) screener na Sparku — periodicky počítá dealer gamma z options OI a
# PUSHuje snapshot na tradezer.app (/api/gamma/ingest). Yahoo options blokuje datacentra,
# ale Spark je za rezidenční IP → funguje (Vercel na Spark nedosáhne → push-only).
#
# Secret-free (klíč z env), vzor jako run_discovery_spark.sh:
#   TRADEZER_TOKEN    — X-Internal-Token pro push (=INTERNAL_API_TOKEN)
#   TRADEZER_BASE_URL — cíl (default https://tradezer.app)
#
# Nasazení na Spark (repo tam NENÍ — jen 2 stdlib soubory):
#   mkdir -p ~/tradezer && cd ~/tradezer
#   curl -fsSL -o gamma_scan.py        https://raw.githubusercontent.com/Martyxl/TradeZer/main/data/gamma_scan.py
#   curl -fsSL -o run_gamma_spark.sh   https://raw.githubusercontent.com/Martyxl/TradeZer/main/data/run_gamma_spark.sh
#   chmod +x run_gamma_spark.sh
# Jednorázově:  TRADEZER_TOKEN=... ./run_gamma_spark.sh
# Smyčka:       LOOP=1 TRADEZER_TOKEN=... nohup ./run_gamma_spark.sh &
#               (INTERVAL sekund mezi běhy, default 3600 = 1 h; OI je EOD, klidně 1×/den)
set -uo pipefail
cd "$(dirname "$0")"
: "${TRADEZER_TOKEN:?nastav TRADEZER_TOKEN (=INTERNAL_API_TOKEN)}"
INTERVAL="${INTERVAL:-3600}"

run() {
  echo "[$(date -Is)] gamma scan…"
  python3 gamma_scan.py --push --no-file
}

if [ "${LOOP:-0}" = "1" ]; then
  while true; do
    run || echo "[$(date -Is)] scan selhal, zkusím za ${INTERVAL}s"
    sleep "$INTERVAL"
  done
else
  run
fi
