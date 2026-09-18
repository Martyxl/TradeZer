#!/usr/bin/env bash
# Discovery screener na Sparku — periodicky skenuje momentum univerzum a PUSHuje
# snapshot na tradezer.app (/api/discovery/ingest). Yahoo blokuje datacentra, ale
# Spark je za rezidenční IP → funguje (Vercel na Spark nedosáhne, proto push-only).
#
# Secret-free (klíče z env), stejný vzor jako run_vision_worker_spark.sh:
#   FINNHUB_API_KEY   — market-cap filtr (<$50B) + earnings katalyzátor (zdarma)
#   TRADEZER_TOKEN    — X-Internal-Token pro push (=INTERNAL_API_TOKEN, stejný jako predictor)
#   TRADEZER_BASE_URL — cíl (default https://tradezer.app)
#
# Nasazení na Spark (repo tam NENÍ — jen 2 stdlib soubory, jako vision worker):
#   mkdir -p ~/tradezer && cd ~/tradezer
#   curl -fsSL -o discovery_scan.py       https://raw.githubusercontent.com/Martyxl/TradeZer/main/data/discovery_scan.py
#   curl -fsSL -o run_discovery_spark.sh  https://raw.githubusercontent.com/Martyxl/TradeZer/main/data/run_discovery_spark.sh
#   chmod +x run_discovery_spark.sh
# Jednorázově:  FINNHUB_API_KEY=... TRADEZER_TOKEN=... ./run_discovery_spark.sh
# Smyčka:       LOOP=1 FINNHUB_API_KEY=... TRADEZER_TOKEN=... nohup ./run_discovery_spark.sh &
#               (INTERVAL sekund mezi běhy, default 21600 = 6 h)
set -uo pipefail
cd "$(dirname "$0")"
: "${TRADEZER_TOKEN:?nastav TRADEZER_TOKEN (=INTERNAL_API_TOKEN)}"
INTERVAL="${INTERVAL:-21600}"

run() {
  echo "[$(date -Is)] discovery scan…"
  python3 discovery_scan.py --push --no-file
}

if [ "${LOOP:-0}" = "1" ]; then
  while true; do
    run || echo "[$(date -Is)] scan selhal, zkusím za ${INTERVAL}s"
    sleep "$INTERVAL"
  done
else
  run
fi
