#!/usr/bin/env bash
# Stahuje 5m data z Dukascopy po měsíčních dávkách (roční rozsah v jednom requestu selhává).
# Použití: ./download.sh <instrument>   (např. xauusd, usatechidxusd)
set -u
INSTRUMENT="$1"
DIR="$(cd "$(dirname "$0")" && pwd)/raw"
mkdir -p "$DIR"

MONTHS=(
  "2025-07-01 2025-08-01" "2025-08-01 2025-09-01" "2025-09-01 2025-10-01"
  "2025-10-01 2025-11-01" "2025-11-01 2025-12-01" "2025-12-01 2026-01-01"
  "2026-01-01 2026-02-01" "2026-02-01 2026-03-01" "2026-03-01 2026-04-01"
  "2026-04-01 2026-05-01" "2026-05-01 2026-06-01" "2026-06-01 2026-07-01"
  "2026-07-01 2026-07-09"
)

FAIL=0
for m in "${MONTHS[@]}"; do
  read -r FROM TO <<< "$m"
  OUT="$DIR/${INSTRUMENT}-m5-bid-${FROM}-${TO}.csv"
  if [ -s "$OUT" ]; then
    echo "SKIP $FROM (exists)"
    continue
  fi
  echo "=== $INSTRUMENT $FROM -> $TO"
  ok=0
  for attempt in 1 2 3; do
    npx -y dukascopy-node -i "$INSTRUMENT" -from "$FROM" -to "$TO" -t m5 -f csv -v true \
      --retries 5 --directory "$DIR" >/dev/null 2>&1 && { ok=1; break; }
    echo "  retry $attempt failed, waiting 10s..."
    sleep 10
  done
  if [ "$ok" -eq 0 ]; then
    echo "FAILED: $FROM"
    FAIL=1
  fi
done

echo "---"
ls -la "$DIR" | grep "$INSTRUMENT" || true
exit $FAIL
