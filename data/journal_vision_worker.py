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

# Default = backend PŘÍMO (ne přes frontend proxy tradezer.app) — interní worker
# šetří requesty na frontend projektu (Vercel edge). Přepiš přes TRADEZER_API.
API = os.environ.get("TRADEZER_API", "https://trade-zer.vercel.app").rstrip("/")
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
    '{"instrument": string|null, "timeframe": string|null, '
    '"tool_top_price": number|null, "tool_boundary_price": number|null, '
    '"tool_bottom_price": number|null, "tool_left_x": number|null, '
    '"time_axis": [{"t": "HH:MM", "x": number}, ...], "entry_time": string|null, '
    '"snapshot_created": string|null, "first_edge_reached": "top"|"bottom"|"none", '
    '"setup": string|null, "notes": string|null}\n'
    "Použij null u čehokoli, co není jasně vidět. NEVYMÝŠLEJ si čísla. Ceny jsou čistá čísla "
    "bez měny a oddělovačů tisíců. notes = 1–2 věty česky shrnující nakreslenou analýzu.\n"
    "POZICE: na grafu je nakreslený position tool = svislá dvojice SOUVISLÝCH obdélníkových "
    "bloků nad sebou (horní a dolní), které se stýkají ve vodorovné hranici. Jejich barvy jsou "
    "u každého uživatele jiné (často zelená/červená, ale i modrá, fialová, šedá…) — BARVY "
    "IGNORUJ, NEURČUJ podle nich směr ani role. Směr, stop i target NEURČUJ — jen přečti "
    "TŘI ceny podle polohy:\n"
    "  tool_top_price = cena HORNÍ vodorovné hrany horního bloku,\n"
    "  tool_boundary_price = cena vodorovné hranice, kde se oba bloky stýkají,\n"
    "  tool_bottom_price = cena DOLNÍ vodorovné hrany dolního bloku.\n"
    "Musí platit tool_top_price > tool_boundary_price > tool_bottom_price.\n"
    "ČAS VSTUPU: vezmi LEVOU svislou hranu position toolu (tam bloky začínají = vstup do "
    "obchodu) a sleduj ji dolů na vodorovnou ČASOVOU OSU. Osa má popisky času po pravidelných "
    "krocích. Uveď VODOROVNÉ PIXELOVÉ souřadnice x (0 = levý okraj obrázku, rozměr obrázku "
    "je uveden v zadání uživatele): tool_left_x = x levé svislé hrany toolu; time_axis = "
    "právě 4 časové popisky osy NEJBLÍŽE té hrany (2 vlevo a 2 vpravo od ní), zleva doprava, "
    "každý jako {t: HH:MM, x: střed popisku v px}. Hrana většinou NENÍ přesně na popisku. "
    "entry_time = tvůj odhad času hrany (HH:MM). "
    "snapshot_created = DOSLOVNÝ text data a času z horního řádku grafu ('created with "
    "TradingView.com, Oct 06, 2026 11:23 UTC+2' → 'Oct 06, 2026 11:23 UTC+2'), jinak null.\n"
    "VÝSLEDEK: first_edge_reached = kterou VNĚJŠÍ vodorovnou hranu toolu (horní = "
    "tool_top_price, dolní = tool_bottom_price) cena PO VSTUPU (svíčky vpravo od levé hrany "
    "toolu) PRVNÍ dosáhla — svíčka (i knot) musí hranu skutečně protnout nebo se jí dotknout. "
    "'none' = žádnou nedosáhla (cena zůstala uvnitř, obchod běží) NEBO si nejsi jistý. "
    "NEODHADUJ: při pochybnosti 'none'.\n"
    "POUZE NAKRESLENÝ OBCHOD: soustřeď se VÝHRADNĚ na position tool (dva bloky nad sebou). "
    "IGNORUJ všechno ostatní — volume profil vpravo, VWAP, session čáry, Fibonacci, "
    "indikátory dole i cenové štítky, které k toolu NEpatří (na grafu je hodně rušivých "
    "prvků). Cenu KAŽDÉ ze 3 úrovní odečti tak, že danou VODOROVNOU hranu sleduješ doprava "
    "k CENOVÉ OSE a přečteš číslo tam. U vysokého RR i malá chyba mění výsledek."
)


def resolve_position(ex: dict) -> dict:
    """Z TŘÍ cen podle polohy (horní hrana / hranice / dolní hrana) deterministicky určí
    entry/stop/target/direction/rr. Role nezávisí na barvách: MENŠÍ blok je strana stopu
    (stop se obvykle dává blíž než target). Horní blok menší → SHORT (stop nahoře);
    dolní menší → LONG (stop dole). Při remíze nebo chybějících cenách nic nedomýšlí."""
    def num(k):
        v = ex.pop(k, None)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    top, mid, bot = num("tool_top_price"), num("tool_boundary_price"), num("tool_bottom_price")
    if top is None or mid is None or bot is None or not (top > mid > bot):
        return ex
    upper, lower = top - mid, mid - bot
    if abs(upper - lower) < 1e-9:
        return ex  # remíza — nelze určit, nech na uživateli
    entry = mid
    if upper < lower:  # menší blok nahoře → SHORT
        direction, stop, target = "short", top, bot
    else:              # menší blok dole → LONG
        direction, stop, target = "long", bot, top
    risk = abs(entry - stop)
    ex.update(direction=direction, entry=entry, stop=stop, target=target,
              rr=round(abs(target - entry) / risk, 2) if risk else None)
    # Výsledek: model jen řekne kterou vnější hranu cena první dosáhla, role určí kód.
    edge = str(ex.get("first_edge_reached") or "").lower().strip()
    reached = {"top": top, "bottom": bot}.get(edge)
    if reached is not None:
        ex["outcome"] = "win" if reached == target else "loss"
    else:
        ex["outcome"] = "open"
    return ex


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _time_from_axis(left_x, axis) -> int | None:
    """Minuty od půlnoci pro x levé hrany toolu: lineární regrese čas~x přes všechny popisky
    osy (průměruje chyby jednotlivých odhadů x). Minimum 3 popisky, rostoucí čas a kladná
    směrnice, jinak None (volající spadne na entry_time odhad modelu)."""
    try:
        lx = float(left_x)
        pts = []
        for p in axis:
            m = re.search(r"(\d{1,2}):(\d{2})", str(p.get("t", "")))
            if m:
                pts.append([float(p["x"]), int(m.group(1)) * 60 + int(m.group(2))])
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
    if len(pts) < 3:
        return None
    pts.sort()
    for i in range(1, len(pts)):  # přechod přes půlnoc → dorovnej o den
        while pts[i][1] < pts[i - 1][1] - 720:
            pts[i][1] += 1440
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx == 0:
        return None
    slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
    if slope <= 0:
        return None
    return round(my + slope * (lx - mx)) % 1440


def resolve_entry_time(ex: dict) -> dict:
    """Složí `traded_at` (YYYY-MM-DDTHH:MM, čas ve svíčkách grafu = časová zóna grafu) z
    entry_time (HH:MM z osy) + data snapshotu z hlavičky. Když by vstup vyšel PO snapshotu,
    patří předchozímu dni. Při nečitelném vstupu nic nedomýšlí."""
    from datetime import datetime, timedelta
    et = str(ex.pop("entry_time", "") or "")
    snap = str(ex.pop("snapshot_created", "") or "")
    lx = ex.pop("tool_left_x", None)
    axis = ex.pop("time_axis", None)
    fit = _time_from_axis(lx, axis)
    if fit is not None:
        et = f"{fit // 60:02d}:{fit % 60:02d}"
    m_t = re.search(r"(\d{1,2}):(\d{2})", et)
    m_s = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}):(\d{2})", snap)
    if not (m_t and m_s) or m_s.group(1).lower() not in _MONTHS:
        return ex
    try:
        snap_dt = datetime(int(m_s.group(3)), _MONTHS[m_s.group(1).lower()], int(m_s.group(2)),
                           int(m_s.group(4)), int(m_s.group(5)))
        entry_dt = snap_dt.replace(hour=int(m_t.group(1)), minute=int(m_t.group(2)))
    except ValueError:
        return ex
    if entry_dt > snap_dt:
        entry_dt -= timedelta(days=1)
    ex["traded_at"] = entry_dt.strftime("%Y-%m-%dT%H:%M")
    return ex


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


def _size_note(img: bytes) -> str:
    """Rozměr PNG z hlavičky (pro pixelové souřadnice x); jiný formát → bez poznámky."""
    if img[:8] == b"\x89PNG\r\n\x1a\n" and len(img) >= 24:
        w, h = int.from_bytes(img[16:20], "big"), int.from_bytes(img[20:24], "big")
        return f" Obrázek má rozměr {w}×{h} px."
    return ""


def vision_extract(img: bytes, media: str) -> tuple[dict, dict]:
    """Nativní Ollama /api/chat — think:false (vypne reasoning → rychlé + krátké) +
    format:json (grammar-constrained validní JSON). Obrázek jako base64 v images[]."""
    b64 = base64.standard_b64encode(img).decode("ascii")  # bez data: prefixu (Ollama)
    body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": "Analyzuj graf a vrať výsledek jako JSON objekt dle schématu." + _size_note(img),
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
    return resolve_entry_time(resolve_position(_parse_json_obj(text))), meta


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
