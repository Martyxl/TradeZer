"""Převezme pojmy z Legendy (web/app/(app)/legenda/page.tsx, pole TERMS) do api/app/help/glossary_data.py
(Python modul — na Vercelu se spolehlivě přibalí, na rozdíl od datových souborů).

Legenda je jediný zdroj pravdy; chatovací pomocník (api/app/routers/help.py) z ní čerpá vysvětlení.
Spuštění po úpravě Legendy:  py api/scripts/sync_glossary.py
Test tests/test_help.py hlídá, že modul odpovídá Legendě.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGEND = ROOT / "web" / "app" / "(app)" / "legenda" / "page.tsx"
OUT = ROOT / "api" / "app" / "help" / "glossary_data.py"

_FIELD = re.compile(r'(term|abbr|cat|desc|calc):\s*"((?:[^"\\]|\\.)*)"', re.S)


def parse_terms(src: str) -> list[dict]:
    body = src[src.index("const TERMS"):]
    body = body[: body.index("];")]
    terms = []
    for block in re.split(r"\n\s*\{\s*(?=term:)", body)[1:]:
        fields = {k: json.loads(f'"{v}"') for k, v in _FIELD.findall(block)}
        if "term" in fields and "desc" in fields:
            terms.append({k: fields.get(k) for k in ("term", "abbr", "cat", "desc", "calc") if fields.get(k)})
    return terms


def render(terms: list[dict]) -> str:
    header = ('"""GENEROVÁNO z Legendy (web/app/(app)/legenda/page.tsx) skriptem '
              'api/scripts/sync_glossary.py — neupravovat ručně."""')
    return header + "\n" + "GLOSSARY = " + json.dumps(terms, ensure_ascii=False, indent=1) + "\n"


def main() -> None:
    terms = parse_terms(LEGEND.read_text(encoding="utf-8"))
    OUT.write_text(render(terms), encoding="utf-8")
    print(f"{len(terms)} pojmů -> {OUT}")


if __name__ == "__main__":
    main()
