"""Kontrola čísel v analýzách výsledků (Spark worker scripts/spark/earnings_watch.py)."""
import importlib.util
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[2] / "scripts" / "spark" / "earnings_watch.py"
_spec = importlib.util.spec_from_file_location("earnings_watch", _P)
ew = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ew)

PRESS = """NVIDIA Announces Financial Results for Third Quarter Fiscal 2027
Revenue of $57.0 billion, up 22% from Q2 and up 62% from a year ago. Data Center revenue of $51.2 billion.
GAAP earnings per diluted share for the quarter were $1.30; non-GAAP earnings per diluted share were $1.30.
Gross margin was 73.4%. Outlook: revenue is expected to be $65.0 billion, plus or minus 2%.
(in millions, except per share data)   Revenue  57,006   35,082   Net income  31,910
Diluted  $ 1.30  $ 0.78
"""
EPS = {"eps_estimate": 1.25, "n_estimates": 18}


def _data(**kw):
    d = {"fiscal_period": "Q3 2027", "revenue_usd": 57006000000, "revenue_yoy_pct": 62, "eps_gaap": 1.30,
         "eps_adjusted": 1.30, "verdict": "positive",
         "headline_cs": "Tržby 57,0 mld. USD a zisk na akcii 1,30 USD proti odhadu 1,25 USD.",
         "summary_cs": ["Tržby vzrostly meziročně o 62 % na 57 mld. USD.",
                        "Datová centra přinesla 51,2 mld. USD.",
                        "Hrubá marže 73,4 %, čistý zisk 31 910 mil. USD."],
         "guidance_cs": "Na příští kvartál čeká tržby 65 mld. USD ± 2 %."}
    d.update(kw)
    return d


def test_correct_numbers_in_czech_formats_pass():
    srcs = ew.source_numbers(PRESS) + ew.eps_facts(EPS, _data())[0]
    u = ew.unverified(_data(), srcs)
    assert ew._n_bad(u) == 0, u


def test_unit_confusion_and_invented_numbers_caught():
    d = _data(eps_adjusted=1.45, revenue_usd=59e9,
              headline_cs="Zisk na akcii 1,45 USD překonal odhad.",
              summary_cs=["Tržby vzrostly o 62 %.", "Zpětný odkup akcií za 1,3 mld. USD.",   # 1,30 je EPS, ne miliardy
                          "Provozní zisk 40,1 mld. USD."])
    srcs = ew.source_numbers(PRESS) + ew.eps_facts(EPS, d)[0]
    u = ew.unverified(d, srcs)
    assert set(u["fields"]) == {"eps_adjusted", "revenue_usd"}
    assert u["headline"] == ["1,45 USD"]
    assert set(u["summary"]) == {1, 2}


def test_surprise_pct_vs_consensus_is_allowed():
    d = _data(summary_cs=["Zisk na akcii překonal odhad o 4 %."])     # (1.30-1.25)/1.25 = 4 %
    srcs = ew.source_numbers(PRESS) + ew.eps_facts(EPS, d)[0]
    assert ew._n_bad(ew.unverified(d, srcs)) == 0
    assert "NAD odhadem" in ew.eps_facts(EPS, d)[1]


def test_fact_check_model_fixes_then_strips_rest(monkeypatch):
    bad = _data(headline_cs="Zisk na akcii 1,45 USD nad odhadem 1,25 USD.", eps_adjusted=1.45,
                summary_cs=["Tržby 57 mld. USD.", "Odkup akcií 9,9 mld. USD.", "Marže 73,4 %."])
    calls = []

    def fake_llm(system, user, max_tokens):
        calls.append(user)
        fixed = dict(bad, headline_cs="Zisk na akcii 1,30 USD nad odhadem 1,25 USD.", eps_adjusted=1.30)
        return ew.json.dumps(fixed, ensure_ascii=False)      # odkup 9,9 mld. model neopravil
    monkeypatch.setattr(ew, "llm", fake_llm)
    out = ew.fact_check("NVDA", PRESS, EPS, bad)
    assert "1,45 USD" in calls[0] and "9,9 mld. USD" in calls[0]        # model dostal, co nesedí
    assert out["headline_cs"].startswith("Zisk na akcii 1,30") and out["eps_adjusted"] == 1.30
    assert out["summary_cs"] == ["Tržby 57 mld. USD.", "Marže 73,4 %."]
    assert out["fact_check"] == {"before": 3, "after": 1, "fixed_by_model": True}


def test_fact_check_without_model_and_unverifiable_headline(monkeypatch):
    monkeypatch.setattr(ew, "llm", lambda *a: None)
    d = _data(headline_cs="Tržby 99 mld. USD.", summary_cs=["Marže 73,4 %.", "Tržby 57 mld. USD."])
    out = ew.fact_check("NVDA", PRESS, EPS, d)
    assert out["headline_cs"] == "Marže 73,4 %." and out["summary_cs"] == ["Tržby 57 mld. USD."]
    assert ew.fact_check("NVDA", PRESS, EPS, _data(headline_cs="Tržby 99 mld. USD.", summary_cs=["Zisk 5 mld. USD."])) is None


def test_explanation_drops_bullets_with_unknown_numbers():
    ctx = "Shrnutí: Tržby 57,0 mld. USD\nEPS 1.3 vs. konsenzus 1.25\nReakce ceny od zveřejnění: +3.25 %"
    out = ew.check_explanation("- Akcie roste o 3,3 % díky tržbám 57 mld. USD.\n- Trh čeká výhled 70 mld. USD.\n"
                               "- Investoři oceňují překonání odhadu.", ctx)
    assert out.splitlines() == ["- Akcie roste o 3,3 % díky tržbám 57 mld. USD.", "- Investoři oceňují překonání odhadu."]


@pytest.mark.parametrize("text,value", [("102,3 mld. USD", 102.3e9), ("1 234 mil. USD", 1234e6), ("0,18 USD", 0.18),
                                        ("15 %", 15), ("45 centů", 0.45), ("2,5 bilionu USD", 2.5e12)])
def test_claim_parsing(text, value):
    c = ew.claims(text)
    assert len(c) == 1 and c[0]["value"] == pytest.approx(value)
