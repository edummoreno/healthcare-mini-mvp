from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import re
import yaml


@dataclass(frozen=True)
class Suggestion:
    specialty: str
    confidence: float
    matched_keywords: List[str]
    why: str
    next_step: str
    disclaimer: str


def _normalize(text: str) -> str:
    text = text.strip().lower()
    # Normalização simples (sem remover acentos pra manter PT-BR direto).
    # Se quiser evoluir: unidecode.
    text = re.sub(r"\s+", " ", text)
    return text


def load_rules(path: str = "rules.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def suggest_specialty(user_text: str, rules: Dict[str, Any]) -> Suggestion:
    text = _normalize(user_text)

    best: Tuple[int, Dict[str, Any], List[str]] | None = None  # (score, spec, matches)

    for spec in rules.get("specialties", []):
        matches: List[str] = []
        for kw in spec.get("keywords", []):
            nkw = _normalize(kw)
            if nkw and nkw in text:
                matches.append(kw)

        score = len(matches)
        if best is None or score > best[0]:
            best = (score, spec, matches)

    disclaimer = (
        "⚠️ Importante: isto NÃO é diagnóstico, NÃO é prescrição e NÃO define urgência. "
        "É apenas uma sugestão de especialidade para você orientar o próximo passo."
    )

    # Se não casou nada relevante, fallback
    if best is None or best[0] == 0:
        fb = rules.get("fallback", {})
        return Suggestion(
            specialty=fb.get("name", "Clínica Médica"),
            confidence=float(fb.get("confidence", 0.5)),
            matched_keywords=[],
            why=fb.get("why", "Sugestão padrão."),
            next_step=fb.get("next_step", "Busque uma avaliação com um(a) profissional de saúde."),
            disclaimer=disclaimer,
        )

    _, spec, matches = best

    # Confiança pode subir um pouco com mais matches (simples e explicável)
    base_conf = float(spec.get("confidence", 0.6))
    confidence = min(0.95, base_conf + 0.05 * max(0, len(matches) - 1))

    return Suggestion(
        specialty=spec.get("name", "Clínica Médica"),
        confidence=confidence,
        matched_keywords=matches,
        why=spec.get("why", "Correspondência por palavras-chave."),
        next_step=spec.get("next_step", "Busque uma avaliação com um(a) profissional de saúde."),
        disclaimer=disclaimer,
    )
