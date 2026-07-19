"""Lokální LLM worker — predikce zpráv přes Bionic/Ollama místo cloud API.

Smyčka: GET /api/unpredicted -> klasifikace lokálním modelem (OpenAI-compatible
API) -> POST /api/backfill/predictions. Jen odchozí spojení, žádný tunel.

Konfigurace (env nebo výchozí):
  TRADEZER_API      https://tradezer.app
  TRADEZER_TOKEN    interní token
  LLM_BASE_URL      http://localhost:11434/v1   (Ollama; Bionic má vlastní port)
  LLM_API_KEY       API klíč (Bionic vyžaduje, Ollama ne — pak libovolný string)
  LLM_MODEL         např. qwen2.5-coder:7b

Použití:
  py local_predictor.py              # jeden průchod
  py local_predictor.py --loop 300   # smyčka à 5 minut
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

API = os.environ.get("TRADEZER_API", "https://tradezer.app")
TOKEN = os.environ.get("TRADEZER_TOKEN", "tradezer-secret-2026")
LLM_BASE = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_KEY = os.environ.get("LLM_API_KEY", "local")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")

SYSTEM_PROMPT = (Path(__file__).parent / "local_classifier_prompt.md").read_text(encoding="utf-8")


def http_json(url: str, method: str = "GET", body: dict | None = None,
              headers: dict | None = None, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        url, method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def classify(title: str, body: str, tickers: list[str]) -> dict | None:
    """Jeden call lokálního modelu pro všechny tickery zprávy."""
    user = f"Tickers: {', '.join(tickers)}\n\nNews:\nTitle: {title}\n"
    if body:
        user += f"Content: {body[:2000]}"
    try:
        resp = http_json(
            f"{LLM_BASE}/chat/completions", "POST",
            {
                "model": LLM_MODEL,
                "temperature": 0.1,
                "max_tokens": 350 * len(tickers) + 200,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
            },
            headers={"Authorization": f"Bearer {LLM_KEY}"},
        )
        text = resp["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        print(f"  LLM error: {e}")
        return None


def run_once() -> int:
    data = http_json(f"{API}/api/unpredicted?limit=10", headers={"X-Internal-Token": TOKEN})
    items = data.get("items", [])
    if not items:
        print("Žádné nepredikované zprávy.")
        return 0

    records = []
    for item in items:
        tickers = item["tickers"]
        print(f"[{item['news_id']}] {item['title'][:70]} -> {tickers}")
        result = classify(item["title"], item.get("body", ""), tickers)
        if not result:
            continue
        for t in tickers:
            c = result.get(t)
            if not isinstance(c, dict):
                print(f"  chybí klasifikace pro {t}")
                continue
            probs = c.get("raw_direction_probs", {})
            total = sum(v for v in probs.values() if isinstance(v, (int, float))) or 1.0
            records.append({
                "news_id": item["news_id"],
                "ticker": t,
                "prob_down": round(float(probs.get("down", 0.333)) / total, 4),
                "prob_neutral": round(float(probs.get("neutral", 0.334)) / total, 4),
                "prob_up": round(float(probs.get("up", 0.333)) / total, 4),
                "confidence": float(c.get("llm_confidence", 0.5)),
                "relevance_score": float(c.get("relevance_score", 0.5)),
                "categories": [str(x) for x in c.get("categories", [])][:6],
                "reasoning": str(c.get("reasoning", ""))[:900],
                "source_weight": item.get("source_weight", 0.5),
                "model_version": f"local-{LLM_MODEL}",
            })

    if not records:
        print("Nic k odeslání.")
        return 0
    result = http_json(
        f"{API}/api/backfill/predictions", "POST",
        {"records": records}, headers={"X-Internal-Token": TOKEN},
    )
    print(f"Odesláno: {result}")
    return result.get("saved", 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, metavar="SEC", help="opakuj každých SEC sekund")
    args = ap.parse_args()

    print(f"Worker: {LLM_MODEL} @ {LLM_BASE} -> {API}")
    if not args.loop:
        run_once()
        return
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"Chyba průchodu: {e}")
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
