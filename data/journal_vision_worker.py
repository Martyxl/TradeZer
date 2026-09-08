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
LLM_MODEL = os.environ.get("LLM_VISION_MODEL", "vision")  # alias na LiteLLM bráně (nepoužito pro vision)

# Vision jde PŘÍMO na Ollamu (ne přes LiteLLM) — nativní think:false + format:json,
# které LiteLLM s drop_params zahazuje. Worker běží na DGX → localhost:11434.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "hf.co/ggml-org/Qwen3.8-27B-GGUF:Q8_0")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_IMG = 8 * 1024 * 1024

SYSTEM_PROMPT = (
    "Jsi asistent obchodního deníku. Uživatel pošle screenshot z TradingView s nakreslenou "
    "analýzou a obchodem. Vytěž strukturované informace. Klidně nejdřív stručně uvažuj, ale "
    "POSLEDNÍ částí odpovědi MUSÍ být validní JSON objekt dle tohoto schématu (za ním už nic):\n"
    '{"instrument": string|null, "direction": "long"|"short"|null, "timeframe": string|null, '
    '"entry": number|null, "stop": number|null, "target": number|null, "rr": number|null, '
    '"setup": string|null, "notes": string|null}\n'
    "Použij null u čehokoli, co není jasně vidět. NEVYMÝŠLEJ si čísla. Ceny jsou čistá čísla "
    "bez měny a oddělovačů tisíců. notes = 1–2 věty česky shrnující nakreslenou analýzu.\n"
    "POZICE: na grafu je nakreslený position tool = obdélník se ZELENOU (cíl/profit) a "
    "ČERVENOU (stop) zónou — tyto barvy platí pro OBA směry! NEPŘEDPOKLÁDEJ 'zelená=long'. "
    "Směr urči podle VZÁJEMNÉ POLOHY zón: ZELENÁ zóna POD červenou → SHORT (cíl je dole); "
    "ZELENÁ NAD červenou → LONG. stop = vzdálená hrana ČERVENÉ zóny, target = vzdálená hrana "
    "ZELENÉ zóny, entry = hranice mezi zónami. Ceny vyplň tak, aby platilo: "
    "SHORT → stop > entry > target; LONG → stop < entry < target.\n"
    "PŘESNOST CEN: čti z ČÍSELNÝCH ŠTÍTKŮ, ne odhadem mezi ryskami. Position tool i cenová "
    "osa mají u každé úrovně přesný popisek s cenou; pokud tool zobrazuje entry/stop/target "
    "nebo RR jako text, POUŽIJ ty hodnoty. Zaokrouhluj přesně dle zobrazené ceny."
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


def vision_extract(img: bytes, media: str) -> tuple[dict, dict]:
    """Nativní Ollama /api/chat — think:false (vypne reasoning → rychlé + krátké) +
    format:json (grammar-constrained validní JSON). Obrázek jako base64 v images[]."""
    b64 = base64.standard_b64encode(img).decode("ascii")  # bez data: prefixu (Ollama)
    body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": "Analyzuj graf a vrať výsledek jako JSON objekt dle schématu.",
             "images": [b64]},
        ],
        "think": False,       # Qwen3.8 thinking OFF → žádná dlouhá úvaha (jinak timeout)
        "format": "json",     # grammar-constrained validní JSON
        "stream": False,
        "options": {"temperature": 0, "num_predict": 700},
    }
    t0 = time.time()
    resp = http_json(f"{OLLAMA_URL}/api/chat", "POST", body, timeout=300)
    ms = int((time.time() - t0) * 1000)
    in_tok = resp.get("prompt_eval_count")
    out_tok = resp.get("eval_count")
    meta = {"model": OLLAMA_MODEL, "ms": ms, "in_tokens": in_tok, "out_tokens": out_tok,
            "total_tokens": (in_tok or 0) + (out_tok or 0)}
    text = ((resp.get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError(
            f"prázdná odpověď (done_reason={resp.get('done_reason')}); "
            f"resp={json.dumps(resp, ensure_ascii=False)[:400]}")
    return _parse_json_obj(text), meta


def _parse_json_obj(text: str) -> dict:
    """Tolerantní parse — model píše úvahu a JSON dá na konec. Vytáhne POSLEDNÍ
    vyvážený { … } objekt (i když úvaha obsahuje závorky)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    end = t.rfind("}")
    while end != -1:
        depth = 0
        for i in range(end, -1, -1):
            if t[i] == "}":
                depth += 1
            elif t[i] == "{":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[i:end + 1])
                    except json.JSONDecodeError:
                        break  # zkus předchozí } (vnořená/nevalidní část)
        end = t.rfind("}", 0, end)
    raise RuntimeError(f"model nevrátil JSON: {text[:200]!r}")


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
            extracted, meta = vision_extract(img, media)
            http_json(f"{API}/api/journal/analyze/{jid}/result", "POST",
                      {"extracted": extracted, "meta": meta}, hdr)
            print(f"[job {jid}] OK ({meta.get('ms')}ms, {meta.get('total_tokens')} tok) -> "
                  f"{json.dumps(extracted, ensure_ascii=False)}")
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
    print(f"Spark vision worker | API={API} | ollama={OLLAMA_URL} | model={OLLAMA_MODEL} | think=off")
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
