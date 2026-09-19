#!/usr/bin/env bash
# Smart Money (insider SEC Form 4) screener — periodicky parsuje nejnovější Form 4 a
# PUSHuje snapshot na tradezer.app (/api/smart-money/ingest). SEC jde i z datacentra,
# ale držíme jednotný push-vzor (běží kdekoli s TRADEZER_TOKEN).
#
#   TRADEZER_TOKEN    — X-Internal-Token pro push (=INTERNAL_API_TOKEN)
#   TRADEZER_BASE_URL — cíl (default https://tradezer.app)
#
# Nasazení (Spark nebo kdekoli):
#   curl -fsSL -o smart_money_scan.py     https://raw.githubusercontent.com/Martyxl/TradeZer/main/data/smart_money_scan.py
#   curl -fsSL -o run_smart_money_spark.sh https://raw.githubusercontent.com/Martyxl/TradeZer/main/data/run_smart_money_spark.sh
#   chmod +x run_smart_money_spark.sh
# Jednorázově:  TRADEZER_TOKEN=... ./run_smart_money_spark.sh
# Smyčka:       LOOP=1 TRADEZER_TOKEN=... nohup ./run_smart_money_spark.sh &
#               (INTERVAL sekund, default 7200 = 2 h; Form 4 chodí průběžně přes den)
set -uo pipefail
cd "$(dirname "$0")"
: "${TRADEZER_TOKEN:?nastav TRADEZER_TOKEN (=INTERNAL_API_TOKEN)}"
INTERVAL="${INTERVAL:-7200}"

run() {
  echo "[$(date -Is)] smart money scan…"
  python3 smart_money_scan.py --push --no-file
}

if [ "${LOOP:-0}" = "1" ]; then
  while true; do
    run || echo "[$(date -Is)] scan selhal, zkusím za ${INTERVAL}s"
    sleep "$INTERVAL"
  done
else
  run
fi
