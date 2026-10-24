#!/usr/bin/env python3
"""Spark worker chatovacího pomocníka: vyzvedává otázky z backendu a odpovídá lokálním modelem.

Tok: GET /api/help/pending (hotové zprávy pro model) → LiteLLM /chat/completions → POST /api/help/answer.
Model na Sparku není dostupný z internetu, proto worker sám polluje backend (krátký interval → svižná odpověď).

Env: TRADEZER_TOKEN (povinný), TRADEZER_API (default https://tradezer.app),
     LLM_BASE_URL (default http://127.0.0.1:4000/v1), LLM_API_KEY, HELP_MODEL (default heavy)
Spuštění: python3 help_chat_worker.py --loop 2      (sekundy mezi dotazy na frontu)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("TRADEZER_API", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "").strip()
LLM_BASE = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:4000/v1").rstrip("/")
LLM_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("HELP_MODEL", "heavy")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TradezerHelp/1.0"


def http_json(url: str, method: str = "GET", body: dict | None = None, headers: dict | None = None,
              timeout: int = 30) -> dict:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def ask_model(messages: list[dict]) -> str:
    resp = http_json(f"{LLM_BASE}/chat/completions", "POST",
                     {"model": MODEL, "temperature": 0.2, "max_tokens": 700, "messages": messages},
                     headers={"Authorization": f"Bearer {LLM_KEY}"}, timeout=120)
    return (resp["choices"][0]["message"].get("content") or "").strip()


def run_once() -> int:
    items = http_json(f"{API}/api/help/pending?limit=3", headers={"X-Internal-Token": TOKEN}).get("items", [])
    for it in items:
        t0 = time.time()
        try:
            text = ask_model(it["messages"])
            payload = {"id": it["id"], "answer": text, "model": MODEL, "ms": int((time.time() - t0) * 1000)}
        except Exception as e:  # noqa: BLE001 — chyba modelu = odpověď „error“, web ukáže omluvu
            print(f"[{it['id']}] chyba modelu: {e}", flush=True)
            payload = {"id": it["id"], "answer": "", "model": MODEL, "ms": int((time.time() - t0) * 1000)}
        http_json(f"{API}/api/help/answer", "POST", payload, headers={"X-Internal-Token": TOKEN})
        print(f"[{it['id']}] odpovězeno za {payload['ms']} ms ({len(payload['answer'])} znaků)", flush=True)
    return len(items)


def main() -> None:
    if not TOKEN:
        sys.exit("Chybí TRADEZER_TOKEN")
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=float, default=0, help="sekundy mezi dotazy na frontu (0 = jednou)")
    a = ap.parse_args()
    print(f"Help worker: {MODEL} @ {LLM_BASE} -> {API}", flush=True)
    while True:
        try:
            run_once()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            print(f"Chyba průchodu: {e}", flush=True)
            time.sleep(10)
        if not a.loop:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
