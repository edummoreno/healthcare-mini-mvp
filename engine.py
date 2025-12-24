from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from engine_ruleset import load_ruleset, suggest as suggest_ruleset


@dataclass(frozen=True)
class Suggestion:
    # Mantém o shape que o app.py já usa
    specialty: str
    confidence: float
    matched_keywords: List[str]
    why: str
    next_step: str
    disclaimer: str
    alternatives: List[Dict[str, Any]]


DEFAULT_NEXT_STEP = "Busque uma avaliação com um(a) profissional de saúde."


@lru_cache(maxsize=2)
def load_rules(path: str = "") -> Dict[str, Any]:
    """
    Carrega o ruleset JSON. Prioriza ruleset.v4.json e cai para ruleset.json.
    Cacheado para não reler a cada submit.
    """
    candidates = []
    if path:
        candidates.append(path)
    candidates += ["ruleset.v4.json", "ruleset.json"]

    for p in candidates:
        if Path(p).exists():
            return load_ruleset(p)

    raise FileNotFoundError("Nenhum ruleset encontrado. Esperado: ruleset.v4.json (ou ruleset.json).")


def _confidence_from_score(base_conf: float, score: int) -> float:
    # heurística simples (igual ideia do engine antigo)
    return min(0.95, float(base_conf) + 0.02 * max(0, int(score) - 1))


def suggest_specialty(user_text: str, rules: Dict[str, Any]) -> Suggestion:
    s = suggest_ruleset(user_text, rules)

    # pega confidence base do ruleset
    base_conf = 0.55
    for sp in rules.get("specialties", []):
        if sp.get("id") == s.specialtyId:
            base_conf = float(sp.get("confidence", 0.55))
            break

    confidence = _confidence_from_score(base_conf, s.score)

    matched = (s.strongHits or []) + (s.weakHits or [])

    return Suggestion(
        specialty=s.specialtyName,
        confidence=confidence,
        matched_keywords=matched,
        why=s.why,
        next_step=DEFAULT_NEXT_STEP,
        disclaimer=s.disclaimer,
        alternatives=[],  # se quiser, a gente traz Top-K depois
    )
