from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import re
import unicodedata
import yaml


@dataclass(frozen=True)
class Suggestion:
    specialty: str
    confidence: float
    matched_keywords: List[str]
    why: str
    next_step: str
    disclaimer: str
    alternatives: List[Dict[str, Any]]  # top-k


GENERALISTS = {
    "Clínica Médica",
    "Clinica Medica",
    "Medicina de Família e Comunidade",
    "Medicina de Familia e Comunidade",
}


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def _normalize(text: str) -> str:
    text = str(text).strip().lower()
    text = _strip_accents(text)
    # pontuação -> espaço
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _phrase_matches_with_gaps(text_norm: str, phrase_norm: str, max_gap: int = 2) -> bool:
    """
    Frase por tokens em ordem, permitindo até `max_gap` tokens no meio.
    Ex: "visao embacada" casa com "minha visao esta bem embacada".
    """
    t = text_norm.split()
    p = phrase_norm.split()
    if not p:
        return False

    for start in range(len(t)):
        if t[start] != p[0]:
            continue

        ti = start + 1
        ok = True
        for pj in p[1:]:
            gap = 0
            while ti < len(t) and gap <= max_gap and t[ti] != pj:
                ti += 1
                gap += 1
            if ti >= len(t) or gap > max_gap or t[ti] != pj:
                ok = False
                break
            ti += 1

        if ok:
            return True

    return False


def _kw_matches(text_norm: str, kw_norm: str) -> bool:
    if not kw_norm:
        return False

    if " " in kw_norm:
        return _phrase_matches_with_gaps(text_norm, kw_norm, max_gap=2)

    return re.search(r"\b" + re.escape(kw_norm) + r"\b", text_norm) is not None


def load_rules(path: str = "rules.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_synonyms(text_norm: str, rules: Dict[str, Any]) -> Tuple[str, List[Tuple[str, str]]]:
    """
    No YAML:
      synonyms:
        "dor de cabeça":
          - "cefaleia"
    Se encontrar a variante, injeta o canônico no texto.
    """
    syn = rules.get("synonyms") or {}
    if not isinstance(syn, dict):
        return text_norm, []

    injected: List[str] = []
    hits: List[Tuple[str, str]] = []
    seen = set()

    for canonical, variants in syn.items():
        if not canonical or not isinstance(variants, list):
            continue

        canon_norm = _normalize(canonical)
        if not canon_norm:
            continue

        for v in variants:
            v_str = str(v)
            v_norm = _normalize(v_str)
            if not v_norm:
                continue

            if _kw_matches(text_norm, v_norm):
                key = (v_str, canonical)
                if key not in seen:
                    seen.add(key)
                    hits.append(key)

                injected.append(canon_norm)
                break

    if not injected:
        return text_norm, hits

    return (text_norm + " " + " ".join(injected)).strip(), hits


def suggest_specialty(user_text: str, rules: Dict[str, Any]) -> Suggestion:
    text = _normalize(user_text)
    text, syn_hits = _apply_synonyms(text, rules)

    scoring = rules.get("scoring", {}) or {}
    strong_w = int(scoring.get("strong_weight", 2))
    weak_w = int(scoring.get("weak_weight", 1))
    min_score = int(scoring.get("min_score", 1))
    top_k = int(scoring.get("top_k", 3))

    disclaimer = rules.get(
        "disclaimer",
        "⚠️ Importante: isto NÃO é diagnóstico, NÃO é prescrição e NÃO define urgência. "
        "É apenas uma sugestão de especialidade para orientar o próximo passo.",
    )

    # (score, strong_count, base_conf, spec, matched, is_generalist)
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

        score = strong_w * len(strong_hits) + weak_w * len(weak_hits)
        if score < min_score:
            continue

        candidates.append((score, len(strong_hits), base_conf, spec, strong_hits + weak_hits, is_generalist))

    # fallback
    if not candidates:
        fb = rules.get("fallback", {}) or {}
        return Suggestion(
            specialty=str(fb.get("name", "Clínica Médica")),
            confidence=float(fb.get("confidence", 0.55)),
            matched_keywords=[],
            why=str(fb.get("why", "Sugestão padrão.")),
            next_step=str(fb.get("next_step", "Busque uma avaliação com um(a) profissional de saúde.")),
            disclaimer=disclaimer,
            alternatives=[],
        )

    # Penaliza generalistas se houver sinal claro em não-generalista
    has_clear_specific = any((strong_count > 0 and not is_gen) for (_, strong_count, _, _, _, is_gen) in candidates)
    if has_clear_specific:
        candidates = [c for c in candidates if not c[5]]

    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    top = candidates[: max(1, top_k)]

    score, strong_count, base_conf, spec, matched, _ = top[0]
    confidence = min(0.95, base_conf + 0.02 * max(0, score - 1))

    why = spec.get("why") or spec.get("confidence_reason") or "Correspondência por palavras-chave."
    why = f"{why} (fortes={strong_count}, score={score})"
    if syn_hits:
        why += " | sinônimos: " + ", ".join([f"{v}→{c}" for (v, c) in syn_hits])

    next_step = spec.get("next_step", "Busque uma avaliação com um(a) profissional de saúde.")

    alternatives = []
    for (ws, sc, bc, s, m, _) in top[1:]:
        alternatives.append(
            {"specialty": s.get("name", ""), "confidence": float(bc), "score": int(ws), "strong_hits": int(sc), "matched": m}
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
