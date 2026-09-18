#!/usr/bin/env bash
# Stahuje 5m data z Dukascopy po měsíčních dávkách (roční rozsah v jednom requestu selhává).
# Měsíce se generují dynamicky: posledních N měsíců + aktuální částečný měsíc.
# Použití: ./download.sh <instrument> [months_back=13]   (např. xauusd, usatechidxusd)
set -u
INSTRUMENT="$1"
MONTHS_BACK="${2:-13}"
DIR="$(cd "$(dirname "$0")" && pwd)/raw"
mkdir -p "$DIR"

TODAY=$(date -u +%Y-%m-%d)
CUR_MONTH=$(date -u +%Y-%m-01)

month_add() {  # month_add YYYY-MM-01 N  -> posune o N měsíců
  date -u -d "$1 $2 month" +%Y-%m-01 2>/dev/null || date -u -v"$2"m -j -f %Y-%m-%d "$1" +%Y-%m-01
}

FAILED=0
for ((i = MONTHS_BACK; i >= 1; i--)); do
  FROM=$(month_add "$CUR_MONTH" "-$i")
  TO=$(month_add "$CUR_MONTH" "-$((i - 1))")
  OUT="$DIR/${INSTRUMENT}-m5-bid-${FROM}-${TO}.csv"
  if [ -s "$OUT" ]; then
    echo "SKIP $FROM (exists)"
    continue
  fi
  echo "=== $INSTRUMENT $FROM -> $TO"
  ok=0
  for attempt in 1 2 3 4 5; do
    npx -y dukascopy-node -i "$INSTRUMENT" -from "$FROM" -to "$TO" -t m5 -f csv -v true \
      --retries 5 --directory "$DIR" >/dev/null 2>&1 && { ok=1; break; }
    echo "  retry $attempt failed, waiting 10s..."
    sleep 10
  done
  if [ "$ok" -eq 0 ]; then
    echo "FAILED: $FROM"
    FAILED=$((FAILED + 1))
    rm -f "$OUT"
  fi
  sleep 2   # jemnější tempo vůči Dukascopy (rate-limit)
done

# Aktuální částečný měsíc (vždy znovu — přibývají data)
if [ "$CUR_MONTH" != "$TODAY" ]; then
  echo "=== $INSTRUMENT $CUR_MONTH -> $TODAY (partial)"
  rm -f "$DIR/${INSTRUMENT}-m5-bid-${CUR_MONTH}-${TODAY}.csv"
  npx -y dukascopy-node -i "$INSTRUMENT" -from "$CUR_MONTH" -to "$TODAY" -t m5 -f csv -v true \
    --retries 5 --directory "$DIR" >/dev/null 2>&1 || { echo "FAILED: partial month"; FAILED=$((FAILED + 1)); }
fi

echo "---"
ls -la "$DIR" | grep "$INSTRUMENT" || true
GOT=$(ls -1 "$DIR"/${INSTRUMENT}-m5-bid-*.csv 2>/dev/null | wc -l)
echo "=== $INSTRUMENT: staženo $GOT měsíčních souborů, selhalo $FAILED ==="
# BEST-EFFORT: pár chybějících měsíců NEshazuje workflow (compute jede z toho, co je).
# Fail jen když je dat opravdu málo (Dukascopy nejspíš úplně dole) → ať si toho všimneme.
if [ "$GOT" -lt 6 ]; then
  echo "PŘÍLIŠ MÁLO DAT ($GOT < 6) → fail."
  exit 1
fi
exit 0
