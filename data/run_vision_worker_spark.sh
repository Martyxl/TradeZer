#!/usr/bin/env bash
# Spark (DGX / Linux) vision worker pro obchodní deník.
#
# Vyžaduje v env (stejné hodnoty jako predictor):
#   LLM_API_KEY     klíč Spark LiteLLM brány (sk-spark-...)
#   TRADEZER_TOKEN  interní API token (= INTERNAL_API_TOKEN na Vercelu)
# Volitelně (mají rozumné defaulty ve workeru):
#   LLM_BASE_URL      default http://192.168.50.47:4000/v1
#   LLM_VISION_MODEL  default "vision"
#   TRADEZER_API      default https://tradezer.app
#
# Použití:
#   export LLM_API_KEY=sk-spark-...        # nebo dej do ~/.bashrc / systemd
#   export TRADEZER_TOKEN=...
#   ./run_vision_worker_spark.sh           # popředí (Ctrl+C ukončí)
#   nohup ./run_vision_worker_spark.sh >~/vision_worker.log 2>&1 &   # na pozadí 24/7
set -euo pipefail
: "${LLM_API_KEY:?Nastav LLM_API_KEY (klíč Spark brány) — stejný jako predictor}"
: "${TRADEZER_TOKEN:?Nastav TRADEZER_TOKEN (interní API token) — stejný jako predictor}"
cd "$(dirname "$0")"
echo "Spouštím vision worker (smyčka à 20 s)…"
exec python3 journal_vision_worker.py --loop 20
