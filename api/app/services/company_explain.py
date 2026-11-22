"""Zjednodušený pohled na firmu z Valuation Radaru pro režim Začátečník.

Překládá skóre, metriky a hnací faktory (drivers) do vět, kterým rozumí i člověk bez znalosti
P/E nebo ROIC. Čisté funkce bez DB → testy v api/tests/test_investor.py. Není to investiční
doporučení — jen popis dat, ze kterých Radar počítá verdikt.
"""
from __future__ import annotations

from app.valuation.scoring import _LABEL_CS
from app.valuation.zones import zone, zone_reliability

_KEY_BY_LABEL = {v: k for k, v in _LABEL_CS.items()}

VERDICT_CS = {"LEVNÁ": "Levná", "FÉROVÁ": "Férová cena", "NAPJATÁ": "Napjatá", "PŘEPÁLENÁ": "Přepálená"}
HORIZON_CS = {
    "VHODNÁ K DRŽBĚ": "Celkově vychází jako vhodná k dlouhodobé držbě.",
    "SPÍŠE ANO": "Celkově vychází spíš dobře.",
    "NEUTRÁLNÍ": "Celkově vychází průměrně — nic výjimečného ani varovného.",
    "SPÍŠE NE": "Celkově vychází spíš slabě.",
}


def bucket(verdict: str | None, bubble: bool = False) -> str:
    """Skupina v jednoduchém Radaru: cheap | fair | expensive | unknown."""
    v = (verdict or "").upper()
    if bubble or v in ("NAPJATÁ", "PŘEPÁLENÁ"):
        return "expensive"
    if v == "LEVNÁ":
        return "cheap"
    if v == "FÉROVÁ":
        return "fair"
    return "unknown"


def _n(v, d=0) -> str:
    """Číslo česky (desetinná čárka, mezera jako oddělovač tisíců)."""
    s = f"{abs(v):,.{d}f}".replace(",", " ").replace(".", ",")
    return s[:-2] if d == 1 and s.endswith(",0") else s   # 9,0 → 9


def _pct(v, d=0) -> str:
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{_n(v, d)} %"


def _cheapness(p: float) -> str:
    if p <= 35:
        return f"levnější než obvykle — dražší bývala ve {_n(100 - p)} % své historie"
    if p <= 65:
        return "za cenu kolem svého dlouhodobého průměru"
    return f"dražší než obvykle — levnější bývala v {_n(p)} % své historie"


def reason(key: str, v: float | None) -> str | None:
    """Jedna lidská věta k metrice. None = k metrice nemáme co říct (chybí hodnota)."""
    if v is None:
        return None
    if key == "pctile_pe_fwd":
        return f"Vůči ziskům je akcie {_cheapness(v)}."
    if key == "pctile_ev_ebitda":
        return f"I podle provozního zisku (EV/EBITDA) je {_cheapness(v)}."
    if key == "z_pe_fwd":
        return ("Je levnější než podobné firmy v oboru." if v < -0.3 else
                "Je dražší než podobné firmy v oboru." if v > 0.3 else "Cenou je podobná firmám v oboru.")
    if key == "peg_fwd":
        verdict = "výhodně" if 0 < v <= 1 else "rozumně" if 0 < v <= 2 else "draze"
        return f"Vzhledem k tomu, jak rychle rostou zisky, vychází cena {verdict} (PEG {_n(v, 1)})."
    if key == "eps_growth_ntm":
        return (f"Zisk by měl za 12 měsíců vyrůst asi o {_n(v)} %." if v >= 0
                else f"Zisk by měl za 12 měsíců klesnout asi o {_n(v)} %.")
    if key in ("revenue_growth_ntm", "revenue_yoy_ttm"):
        return f"Tržby rostou asi o {_n(v)} % ročně." if v >= 0 else f"Tržby klesají asi o {_n(v)} % ročně."
    if key == "growth_accel":
        return "Růst zisku se zrychluje." if v > 0 else "Růst zisku zpomaluje."
    if key == "roic":
        q = "vysoce" if v >= 15 else "slušně" if v >= 8 else "málo"
        return f"Peníze vložené do podnikání se jí vrací {q} — asi {_n(v)} % ročně (ROIC)."
    if key == "fcf_margin":
        return (f"Ze 100 Kč tržeb jí zbyde asi {_n(v)} Kč volné hotovosti." if v >= 0
                else "Spotřebuje víc hotovosti, než vydělá.")
    if key == "net_debt_to_ebitda":
        if v < 0:
            return "Má víc hotovosti než dluhů."
        q = "nízký" if v < 1.5 else "střední" if v < 3 else "vysoký"
        return f"Dluh je {q} — splatila by ho z provozního zisku asi za {_n(v, 1)} roku."
    if key == "margin_trend":
        return "Marže (kolik z tržeb zůstane jako zisk) rostou." if v > 0 else "Marže (kolik z tržeb zůstane jako zisk) klesají."
    if key == "share_count_change":
        if v < 0:
            return f"Skupuje vlastní akcie (za rok jich ubylo {_n(v, 1)} %) — tvůj podíl na firmě roste."
        return f"Vydává nové akcie (za rok jich přibylo {_n(v, 1)} %) — podíl akcionářů se ředí."
    if key == "revision_ratio_30d":
        return ("Analytici za poslední měsíc odhady zisku spíš zvyšují." if v > 0.15 else
                "Analytici za poslední měsíc odhady zisku spíš snižují." if v < -0.15 else
                "Analytici odhady zisku za poslední měsíc moc nemění.")
    if key == "estimate_drift_90d":
        return f"Očekávaný zisk se za 3 měsíce změnil o {_pct(v * 100)}."
    if key == "avg_surprise_4q":
        return (f"Poslední výsledky překonaly očekávání v průměru o {_n(v, 1)} %." if v >= 0
                else f"Poslední výsledky zaostaly za očekáváním v průměru o {_n(v, 1)} %.")
    if key == "px_vs_sma200":
        return (f"Cena je {_n(v)} % nad svým průměrem za posledních 200 dní." if v >= 0
                else f"Cena je {_n(v)} % pod svým průměrem za posledních 200 dní.")
    if key == "mom_12_1":
        return f"Za poslední rok se akcie změnila o {_pct(v)}."
    if key == "max_dd_1y":
        return f"Za poslední rok byla v jednu chvíli až o {_n(v)} % níž než na vrcholu."
    return None


# Pět otázek, které si začátečník klade, a z jakých metrik na ně odpovídáme.
PILLARS = [
    ("valuation", "Cena", "Je levná?", ("pctile_pe_fwd", "z_pe_fwd", "peg_fwd")),
    ("growth", "Růst", "Roste?", ("eps_growth_ntm", "revenue_growth_ntm", "revenue_yoy_ttm")),
    ("quality", "Kvalita", "Je to dobrá firma?", ("fcf_margin", "net_debt_to_ebitda", "roic")),
    ("revision", "Analytici", "Co čekají analytici?", ("revision_ratio_30d", "avg_surprise_4q")),
    ("trend", "Trend", "Jak se jí daří na burze?", ("mom_12_1", "px_vs_sma200", "max_dd_1y")),
]


def level(score: float | None) -> str:
    if score is None:
        return "none"
    return "good" if score >= 60 else "ok" if score >= 40 else "weak"


def explain(*, scores: dict, metrics: dict, drivers: dict, verdict: str | None, horizon: str | None,
            bubble: bool, confidence: float | None, growth_basis: str | None = None) -> dict:
    """scores: {valuation, growth, quality, revision, trend, composite}; drivers: {positive, negative}."""
    pillars = []
    for key, label, question, keys in PILLARS:
        texts = [t for t in (reason(k, metrics.get(k)) for k in keys) if t]
        pillars.append({"key": key, "label": label, "question": question, "score": scores.get(key),
                        "level": level(scores.get(key)), "text": " ".join(texts[:2]) or "Na tohle nemáme dost dat."})

    def from_drivers(items: list[dict]) -> list[str]:
        out = []
        for d in items or []:
            k = _KEY_BY_LABEL.get(d.get("name"), d.get("name"))
            t = reason(k, d.get("value"))
            if t and t not in out:
                out.append(t)
        return out

    pctile, growth = metrics.get("pctile_pe_fwd"), metrics.get("eps_growth_ntm")
    z = zone(pctile, growth)
    reliable, note = zone_reliability(growth, growth_basis, confidence)
    v = (verdict or "").upper()
    if bubble:
        headline = "Pozor, cena utekla ziskům — vypadá to na bublinu."
    elif v:
        headline = {"LEVNÁ": "Vychází levně vůči tomu, kolik vydělává.",
                    "FÉROVÁ": "Cena odpovídá tomu, kolik firma vydělává.",
                    "NAPJATÁ": "Cena je spíš napjatá — trh už hodně dobrého započítal.",
                    "PŘEPÁLENÁ": "Vychází draze vůči tomu, kolik vydělává."}.get(v, "")
    else:
        headline = "Pro tuto firmu zatím nemáme hodnocení."
    return {
        "verdict": verdict, "verdict_label": VERDICT_CS.get(v), "bucket": bucket(verdict, bubble),
        "headline": headline, "overall": HORIZON_CS.get((horizon or "").upper()),
        "zone": z, "reliable": reliable and (confidence or 0) >= 0.5, "reliability_note": note,
        "pillars": pillars,
        "pros": from_drivers(drivers.get("positive")), "cons": from_drivers(drivers.get("negative")),
    }


def advice(*, bucket_: str, zone_: str | None, reliable: bool, held_weight: float | None,
           stocks_target: float, plan_label: str) -> dict:
    """Co to znamená pro tebe — podle verdiktu, tvého portfolia a investičního typu."""
    held = held_weight is not None
    w = held_weight or 0
    if not reliable:
        tail = " Data k firmě jsou neúplná, ber hodnocení s rezervou."
    else:
        tail = ""
    if bucket_ == "expensive":
        if held:
            return {"kind": "trim" if w >= 10 else "hold",
                    "text": f"Máš ji ({_n(w, 1)} % portfolia). Nepřikupuj. Pokud máš velký zisk, můžeš zvážit prodej "
                            "části — nejdřív kusy, které držíš přes 3 roky (bez daně)." + tail}
        return {"kind": "wait", "text": "Teď spíš nekupovat — cena předbíhá zisky. Vrať se, až zlevní." + tail}
    if not stocks_target:
        return {"kind": "hold", "text": f"Tvůj typ {plan_label} s jednotlivými akciemi nepočítá — nákupy jdou do fondů."
                + (" Tu, kterou máš, klidně drž." if held else "") + tail}
    if held and w >= 10:
        return {"kind": "hold", "text": f"Už tvoří {_n(w, 1)} % portfolia. Víc nepřidávej — jedna firma max 10 %." + tail}
    if bucket_ == "cheap" and zone_ == "buy" and reliable:
        return {"kind": "buy", "text": ("Vhodná na dokoupení" if held else "Vhodná kandidátka") +
                " do části Vlastní akcie. Jedna firma max 10 % portfolia; kupuj postupně." + tail}
    if bucket_ in ("cheap", "fair"):
        return {"kind": "hold", "text": ("Drž ji. " if held else "") +
                "Férová cena — nákup nespěchá. Když chceš přidat, raději postupně a malými částkami." + tail}
    return {"kind": "hold", "text": ("Drž ji, nic dělat nemusíš." if held else "Bez jasného signálu.") + tail}
