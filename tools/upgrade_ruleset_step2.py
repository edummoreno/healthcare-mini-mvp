# tools/upgrade_ruleset_step2.py
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List
from pathlib import Path

# Reusa a MESMA normalização do engine (copiamos aqui para manter script independente)
import re
import unicodedata


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


SYNONYMS_PTBR_V1: Dict[str, List[str]] = {
    # linguagem do paciente ↔ termos comuns/variantes
    "dor de cabeça": ["cefaleia"],
    "falta de ar": ["dispneia"],
    "desmaio": ["síncope", "sincope"],
    "formigamento": ["parestesia"],
    "dor nas costas": ["lombalgia"],
    "dor no estômago": ["epigastralgia", "dor epigástrica", "dor epigastrica"],
    "azia": ["pirose"],
    "refluxo": ["refluxo gastroesofágico", "refluxo gastroesofagico", "drge"],
    "pressão alta": ["hipertensão", "hipertensao"],
    "infecção urinária": ["itu"],
    "dor ao urinar": ["disúria", "disuria"],
    "cálculo renal": ["nefrolitíase", "nefrolitiase"],
    # plural “barato” (sem stemming)
    "palpitação": ["palpitações", "palpitacoes"],
    "cárie": ["cáries", "caries"],
}


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        k = normalize_text(x)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def merge_synonyms(existing: Dict[str, List[str]]) -> Dict[str, List[str]]:
    out = dict(existing or {})
    for canon, vars_ in SYNONYMS_PTBR_V1.items():
        out.setdefault(canon, [])
        out[canon].extend(vars_)
        out[canon] = dedupe_keep_order(out[canon])
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print("Uso: python tools/upgrade_ruleset_step2.py <ruleset_in.json> <ruleset_out.json>")
        return 2

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    data: Dict[str, Any] = json.loads(in_path.read_text(encoding="utf-8"))

    # bump de versão
    data["version"] = int(data.get("version", 0)) + 1

    # synonyms
    data["synonyms"] = merge_synonyms(data.get("synonyms", {}))

    # marca Clínica Médica como generalista (preparação para penalização)
    for sp in data.get("specialties", []):
        if sp.get("id") == "clinica_medica":
            sp["generalist"] = True

        sp["strong"] = dedupe_keep_order(sp.get("strong", []))
        sp["weak"] = dedupe_keep_order(sp.get("weak", []))

    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[upgrade_ruleset_step2] OK: gerado {out_path} (version={data['version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
