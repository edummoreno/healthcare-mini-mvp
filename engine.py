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
    alternatives: List[Dict[str, Any]]  # Upgrade 3: Top-3 (ou mais)


def _normalize(text: str) -> str:
    text = str(text).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _kw_matches(text_norm: str, kw_norm: str) -> bool:
    """
    Match simples e explicável, com menos falso-positivo:
    - Se keyword tem espaço/hífen/barra, usa substring normalizada.
    - Se keyword é "uma palavra", usa boundary (\b) pra evitar pegar dentro de outras palavras.
    """
    if not kw_norm:
        return False

    if " " in kw_norm or "-" in kw_norm or "/" in kw_norm:
        return kw_norm in text_norm

    pattern = r"\b" + re.escape(kw_norm) + r"\b"
    return re.search(pattern, text_norm) is not None


def load_rules(path: str = "rules.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_semantic_aliases(text_norm: str, rules: Dict[str, Any]) -> str:
    """
    Gancho para Upgrade 4 (normalização semântica).

    Se existir no YAML:
      semantic_aliases:
        SOBREPESO:
          - "acima do peso"
          - "sobrepeso"
          - "obesidade"

    Quando um alias aparece no texto, a engine injeta o token canônico (SOBREPESO) no texto.
    Isso aumenta o recall sem precisar repetir 30 variações em cada especialidade.
    """
    aliases = rules.get("semantic_aliases") or {}
    if not isinstance(aliases, dict):
        return text_norm

    enriched = text_norm
    for token, phrases in aliases.items():
        if not token or not isinstance(phrases, list):
            continue

        token_norm = _normalize(token)
        if not token_norm:
            continue

        for p in phrases:
            pn = _normalize(p)
            if pn and pn in text_norm:
                enriched = enriched + " " + token_norm
                break

    return enriched


def suggest_specialty(user_text: str, rules: Dict[str, Any]) -> Suggestion:
    text = _normalize(user_text)
    text = _apply_semantic_aliases(text, rules)  # Gancho semântico (opcional via YAML)

    scoring = rules.get("scoring", {}) or {}
    strong_w = int(scoring.get("strong_weight", 2))
    weak_w = int(scoring.get("weak_weight", 1))
    top_k = int(scoring.get("top_k", 3))

    GENERALISTS = {
        "Clínica Médica",
        "Clinica Medica",
        "Medicina de Família e Comunidade",
        "Medicina de Familia e Comunidade",
    }

    # candidates tuple:
    # (weighted_score, strong_count, base_conf, spec, matched_list, is_generalist)
    candidates: List[Tuple[int, int, float, Dict[str, Any], List[str], bool]] = []

    for spec in rules.get("specialties", []) or []:
        name = str(spec.get("name", "")).strip()
        if not name:
            continue

        base_conf = float(spec.get("confidence", 0.6))
        is_generalist = name in GENERALISTS

        strong_hits: List[str] = []
        weak_hits: List[str] = []

        for kw in (spec.get("strong_keywords") or []):
            kw_str = str(kw)
            if _kw_matches(text, _normalize(kw_str)):
                strong_hits.append(kw_str)

        for kw in (spec.get("weak_keywords") or []):
            kw_str = str(kw)
            if _kw_matches(text, _normalize(kw_str)):
                weak_hits.append(kw_str)

        # (opcional) compatibilidade com YAML antigo: se alguém ainda usar "keywords"
        # e não definiu strong/weak, trate como weak.
        if not strong_hits and not weak_hits:
            legacy = []
            for kw in (spec.get("keywords") or []):
                kw_str = str(kw)
                if _kw_matches(text, _normalize(kw_str)):
                    legacy.append(kw_str)
            weak_hits.extend(legacy)

        weighted_score = strong_w * len(strong_hits) + weak_w * len(weak_hits)
        if weighted_score <= 0:
            continue

        matched = strong_hits + weak_hits
        candidates.append((weighted_score, len(strong_hits), base_conf, spec, matched, is_generalist))

    disclaimer = rules.get(
        "disclaimer",
        "⚠️ Importante: isto NÃO é diagnóstico, NÃO é prescrição e NÃO define urgência. "
        "É apenas uma sugestão de especialidade para orientar o próximo passo.",
    )

    # fallback se nada casou
    if not candidates:
        fb = rules.get("fallback", {}) or {}
        return Suggestion(
            specialty=fb.get("name", "Clínica Médica"),
            confidence=float(fb.get("confidence", 0.55)),
            matched_keywords=[],
            why=fb.get("why", "Sugestão padrão."),
            next_step=fb.get("next_step", "Busque uma avaliação com um(a) profissional de saúde."),
            disclaimer=disclaimer,
            alternatives=[],
        )

    # Upgrade 2: se houver sinal claro (>=1 strong) em especialidade NÃO-generalista,
    # removemos generalistas da disputa.
    has_clear_specific = any((strong_count > 0 and not is_gen) for (_, strong_count, _, _, _, is_gen) in candidates)
    if has_clear_specific:
        candidates = [c for c in candidates if not c[5]]

    # Ordena por: score ponderado, strong hits, confidence base
    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    # Upgrade 3: top-k
    top = candidates[:max(1, top_k)]
    weighted_score, strong_count, base_conf, spec, matched, _ = top[0]

    # Confiança heurística: base + bônus por evidência (teto)
    confidence = min(0.95, base_conf + 0.02 * max(0, weighted_score - 1))

    why = spec.get("why") or spec.get("confidence_reason") or "Correspondência por palavras-chave."
    why = f"{why} (fortes={strong_count}, score={weighted_score})"

    next_step = spec.get("next_step", "Busque uma avaliação com um(a) profissional de saúde.")

    alternatives = []
    for (ws, sc, bc, s, m, _) in top[1:]:
        alternatives.append(
            {
                "specialty": s.get("name", ""),
                "confidence": float(bc),  # base_conf, não a heurística final
                "score": int(ws),
                "strong_hits": int(sc),
                "matched": m,
            }
        )

    return Suggestion(
        specialty=spec.get("name", "Clínica Médica"),
        confidence=confidence,
        matched_keywords=matched,
        why=why,
        next_step=next_step,
        disclaimer=disclaimer,
        alternatives=alternatives,
    )
