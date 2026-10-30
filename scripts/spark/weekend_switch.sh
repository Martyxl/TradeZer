#!/usr/bin/env bash
# Víkendový útlum Tradezeru na Sparku (aby Neon o víkendu mohl usnout — platíme za čas, kdy je vzhůru).
#
# Spouští tradezer-weekend.timer každých 10 min:
#   - v okně pátek 17:30 → neděle 16:00 ET (viz api/app/weekend.py) zastaví smyčky, které budí Neon,
#     a jednou za hodinu udělá jeden průchod: stažení zpráv + predikce (víkendové zprávy jdou do pondělního biasu);
#   - po konci okna smyčky zase spustí.
# Jedná jen při změně stavu (soubor STATE) — ručně zastavenou službu ve všední den znovu nespouští.
set -uo pipefail

LOOPS="tradezer-refresh tradezer-predictor tradezer-help tradezer-calibrate tradezer-outlookeval
       tradezer-portfolio-quotes tradezer-regime tradezer-vision tradezer-warm tradezer-fund
       tradezer-discovery tradezer-gamma tradezer-smartmoney tradezer-earnings"
T="$HOME/tradezer"
STATE="$T/.weekend_state"
LAST_TICK="$T/.weekend_last_tick"
TICK_EVERY=3600

quiet_now() {
  local dow hm
  dow=$(TZ=America/New_York date +%u)
  hm=$((10#$(TZ=America/New_York date +%H%M)))
  [ "$dow" = 6 ] || { [ "$dow" = 5 ] && [ "$hm" -ge 1730 ]; } || { [ "$dow" = 7 ] && [ "$hm" -lt 1600 ]; }
}

tick() {
  echo "[$(date -Is)] víkendový průchod: zprávy + predikce"
  ( set -a; . <(grep -v '^#' "$T/scans.env"); . <(grep -v '^#' "$T/predictor.env"); set +a
    # db.env obsahuje '&' → nesourcovat, předat přes python-dotenv-like načtení
    DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' "$T/db.env")" \
      bash -c "cd '$T/app/api' && '$T/appvenv/bin/python' -m app.spark_jobs refresh" || echo "refresh selhal"
    python3 "$T/local_predictor.py" || echo "predictor selhal" )
  date +%s > "$LAST_TICK"
}

want=active; quiet_now && want=quiet
have=$(cat "$STATE" 2>/dev/null || echo active)

if [ "$want" != "$have" ]; then
  if [ "$want" = quiet ]; then
    echo "[$(date -Is)] začátek víkendu → zastavuji smyčky"
    systemctl --user stop $LOOPS
  else
    echo "[$(date -Is)] konec víkendu → spouštím smyčky"
    systemctl --user start $LOOPS
  fi
  echo "$want" > "$STATE"
fi

if [ "$want" = quiet ]; then
  last=$(cat "$LAST_TICK" 2>/dev/null || echo 0)
  [ $(( $(date +%s) - last )) -ge $TICK_EVERY ] && tick
fi
exit 0
