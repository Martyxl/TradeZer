"""Spark vision worker pro obchodní deník — async extrakce obchodu z TradingView.

Běží NA Sparku (jako local_predictor.py). Cloud (Vercel) nedosáhne na Spark, takže
worker si sám vyzvedává práci a pushuje výsledky ven (jen odchozí spojení):

  smyčka: GET /api/journal/analyze/pending  (X-Internal-Token)
       -> pro každý job stáhne obrázek grafu ze source_url (TradingView snapshot)
       -> pošle lokálnímu vision modelu (OpenAI-compatible, LiteLLM brána na Sparku)
       -> POST /api/journal/analyze/{id}/result  s vytěženým JSON

Konfigurace (env):
  TRADEZER_API      https://tradezer.app
  TRADEZER_TOKEN    interní API token (X-Internal-Token)
  LLM_BASE_URL      http://192.168.50.47:4000/v1   (Spark LiteLLM brána)
  LLM_API_KEY       klíč brány
  LLM_VISION_MODEL  alias vision modelu na bráně (např. qwen vision)

Použití:
  py journal_vision_worker.py            # jeden průchod
  py journal_vision_worker.py --loop 20  # smyčka à 20 s
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("TRADEZER_API", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "")
if not TOKEN:
    raise SystemExit("Chybí TRADEZER_TOKEN env (interní API token).")
LLM_BASE = os.environ.get("LLM_BASE_URL", "http://192.168.50.47:4000/v1").rstrip("/")
LLM_KEY = os.environ.get("LLM_API_KEY", "local")
LLM_MODEL = os.environ.get("LLM_VISION_MODEL", "vision")  # alias vision modelu na Spark bráně

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_IMG = 8 * 1024 * 1024

SYSTEM_PROMPT = (
    "Jsi asistent obchodního deníku. Uživatel pošle screenshot z TradingView s nakreslenou "
    "analýzou a obchodem. Vytěž strukturované informace a vrať POUZE validní JSON (bez markdownu):\n"
    '{"instrument": string|null, "direction": "long"|"short"|null, "timeframe": string|null, '
    '"entry": number|null, "stop": number|null, "target": number|null, "rr": number|null, '
    '"setup": string|null, "notes": string|null}\n'
    "Použij null u čehokoli, co není jasně vidět. NEVYMÝŠLEJ si čísla. Ceny jsou čistá čísla "
    "bez měny a oddělovačů tisíců. notes = 1–2 věty česky shrnující nakreslenou analýzu.\n"
    "SMĚR urči z GEOMETRIE úrovní, ne z barvy: u SHORT je stop NAD vstupem a target POD "
    "vstupem; u LONG opačně. Pečlivě rozliš stop (za entry, riziko) od target (cíl). "
    "TradingView Short Position = target pod entry, Long Position = target nad entry."
)


def http_json(url: str, method: str = "GET", body: dict | None = None,
              headers: dict | None = None, timeout: int = 90) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_image(url: str) -> tuple[bytes, str]:
    """TradingView snapshot / přímý odkaz → (bytes, media_type)."""
    def _get(u: str):
        req = urllib.request.Request(u, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read(), r.headers.get("Content-Type", "")
    img_url = url
    if not url.lower().split("?")[0].endswith(IMG_EXT):
        html, _ = _get(url)
        m = re.search(rb'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I) \
            or re.search(rb'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
        if not m:
            raise RuntimeError("og:image nenalezen (není to veřejný TradingView snapshot?)")
        img_url = m.group(1).decode()
    data, ctype = _get(img_url)
    if len(data) > MAX_IMG:
        raise RuntimeError("obrázek > 8 MB")
    ctype = ctype.split(";")[0].strip().lower()
    return data, ctype if ctype.startswith("image/") else "image/png"


def vision_extract(img: bytes, media: str) -> dict:
    b64 = base64.standard_b64encode(img).decode("ascii")
    body = {
        "model": LLM_MODEL,
        "max_tokens": 1500,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Vytěž obchod z tohoto grafu jako JSON dle instrukcí."},
                {"type": "image_url", "image_url": {"url": f"data:{media};base64,{b64}"}},
            ]},
        ],
    }
    resp = http_json(f"{LLM_BASE}/chat/completions", "POST", body,
                     {"Authorization": f"Bearer {LLM_KEY}"}, timeout=180)
    choice = resp["choices"][0] if resp.get("choices") else {}
    msg = choice.get("message", {}) if isinstance(choice, dict) else {}
    text = msg.get("content")
    if not text:  # některé reasoning modely dají odpověď sem
        text = msg.get("reasoning_content")
    if isinstance(text, list):  # content jako pole částí
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    if not isinstance(text, str):
        text = str(text or "")
    if not text.strip():
        raise RuntimeError(
            f"prázdná odpověď (finish_reason={choice.get('finish_reason')}); "
            f"resp={json.dumps(resp, ensure_ascii=False)[:400]}")
    return _parse_json_obj(text)


def _parse_json_obj(text: str) -> dict:
    """Tolerantní parse — qwen občas obalí JSON textem/markdownem. Vytáhne { … }."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if not m:
            raise RuntimeError(f"model nevrátil JSON: {text[:200]!r}")
        return json.loads(m.group(0))


def process_once() -> int:
    hdr = {"X-Internal-Token": TOKEN}
    try:
        pending = http_json(f"{API}/api/journal/analyze/pending", headers=hdr).get("jobs", [])
    except urllib.error.URLError as e:
        print(f"[pending] chyba: {e}")
        return 0
    done = 0
    for job in pending:
        jid, url = job["id"], job.get("source_url") or ""
        print(f"[job {jid}] {url}")
        try:
            img, media = fetch_image(url)
            extracted = vision_extract(img, media)
            http_json(f"{API}/api/journal/analyze/{jid}/result", "POST",
                      {"extracted": extracted}, hdr)
            print(f"[job {jid}] OK -> {extracted.get('instrument')} {extracted.get('direction')}")
            done += 1
        except Exception as e:  # noqa: BLE001
            print(f"[job {jid}] FAIL: {e}")
            try:
                http_json(f"{API}/api/journal/analyze/{jid}/result", "POST",
                          {"error": str(e)[:400]}, hdr)
            except Exception:  # noqa: BLE001
                pass
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="interval smyčky v sekundách (0 = jeden průchod)")
    args = ap.parse_args()
    print(f"Spark vision worker | API={API} | model={LLM_MODEL} | brána={LLM_BASE}")
    if args.loop <= 0:
        process_once()
        return
    while True:
        try:
            process_once()
        except KeyboardInterrupt:
            print("konec")
            sys.exit(0)
        except Exception as e:  # noqa: BLE001
            print(f"[loop] chyba: {e}")
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
