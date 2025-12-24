from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class Suggestion:
    specialty: str
    confidence: float
    matched_keywords: List[str]
    why: str
    next_step: str
    disclaimer: str
    alternatives: List[Dict[str, Any]]


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def _normalize(text: str) -> str:
    text = str(text).strip().lower()
    text = _strip_accents(text)
    # troca pontuação por espaço (mantém letras/números)
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _kw_matches(text_norm: str, kw_norm: str) -> bool:
    if not kw_norm:
        return False
    # frases (com espaço) -> substring
    if " " in kw_norm:
        return kw_norm in text_norm
    # palavra única -> boundary
    return re.search(r"\b" + re.escape(kw_norm) + r"\b", text_norm) is not None


def load_ruleset(path: str = "ruleset.v4.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f) or {}


def _apply_synonyms(text_norm: str, ruleset: Dict[str, Any]) -> Tuple[str, List[Tuple[str, str]]]:
    """
    synonyms no ruleset:
      "dor de cabeça": ["cefaleia", ...]
    Se encontrar "cefaleia" no texto, injeta "dor de cabeça" no texto normalizado.
    """
    syn = ruleset.get("synonyms") or {}
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

    enriched = (text_norm + " " + " ".join(injected)).strip()
    return enriched, hits


def suggest_specialty(user_text: str, ruleset: Dict[str, Any]) -> Suggestion:
    text = _normalize(user_text)
    text, syn_hits = _apply_synonyms(text, ruleset)

    scoring = ruleset.get("scoring") or {}
    strong_w = int(scoring.get("strongWeight", 2))
    weak_w = int(scoring.get("weakWeight", 1))
    min_score = int(scoring.get("minScore", 1))
    top_k = int(scoring.get("topK", 3))

    disclaimer = ruleset.get(
        "disclaimer",
        "⚠️ Importante: isto NÃO é diagnóstico, NÃO é prescrição e NÃO define urgência. "
        "É apenas uma sugestão de especialidade para orientar o próximo passo.",
    )

    # (score, strong_count, base_conf, spec, matched_list)
    candidates: List[Tuple[int, int, float, Dict[str, Any], List[str]]] = []

    for spec in ruleset.get("specialties") or []:
        name = str(spec.get("displayName", "")).strip()
        if not name:
            continue

        base_conf = float(spec.get("confidence", 0.6))
        strong_hits: List[str] = []
        weak_hits: List[str] = []

        for kw in spec.get("strong") or []:
            kw_str = str(kw)
            if _kw_matches(text, _normalize(kw_str)):
                strong_hits.append(kw_str)

        for kw in spec.get("weak") or []:
            kw_str = str(kw)
            if _kw_matches(text, _normalize(kw_str)):
                weak_hits.append(kw_str)

        weighted_score = strong_w * len(strong_hits) + weak_w * len(weak_hits)
        if weighted_score < min_score:
            continue

        candidates.append((weighted_score, len(strong_hits), base_conf, spec, strong_hits + weak_hits))

    if not candidates:
        # fallback
        fb_id = ruleset.get("fallbackSpecialtyId", "clinica_medica")
        # tenta achar displayName do fallback
        fb_name = "Clínica Médica"
        for s in ruleset.get("specialties") or []:
            if s.get("id") == fb_id:
                fb_name = s.get("displayName", fb_name)
                break

        return Suggestion(
            specialty=fb_name,
            confidence=0.55,
            matched_keywords=[],
            why="Sugestão padrão (sem correspondência forte suficiente).",
            next_step="Busque uma avaliação com um(a) profissional de saúde.",
            disclaimer=disclaimer,
            alternatives=[],
        )

    # Upgrade 2 (mesma ideia): se existe especialidade não-generalista com strong>0, remove generalistas
    has_clear_specific = any(sc > 0 and not bool(spec.get("generalist", False)) for (_, sc, _, spec, _) in candidates)
    if has_clear_specific:
        candidates = [c for c in candidates if not bool(c[3].get("generalist", False))]

    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    top = candidates[: max(1, top_k)]
    weighted_score, strong_count, base_conf, spec, matched = top[0]
    confidence = min(0.95, base_conf + 0.02 * max(0, weighted_score - 1))

    why = spec.get("why", "Correspondência por palavras-chave.")
    why = f"{why} (fortes={strong_count}, score={weighted_score})"
    if syn_hits:
        why += " | sinônimos: " + ", ".join([f"{v}→{c}" for (v, c) in syn_hits])

    next_step = spec.get("next_step", "Busque uma avaliação com um(a) profissional de saúde.")

    alternatives: List[Dict[str, Any]] = []
    for (ws, sc, bc, s, m) in top[1:]:
        alternatives.append(
            {
                "specialty": s.get("displayName", ""),
                "confidence": float(bc),
                "score": int(ws),
                "strong_hits": int(sc),
                "matched": m,
            }
        )

    return Suggestion(
        specialty=spec.get("displayName", "Clínica Médica"),
        confidence=confidence,
        matched_keywords=matched,
        why=why,
        next_step=next_step,
        disclaimer=disclaimer,
        alternatives=alternatives,
    )

# --- compat: alguns testes/arquivos esperam `suggest(...)` ---
def suggest(text: str, ruleset: dict):
    # se sua função principal se chama diferente, troque aqui:
    return suggest_specialty(text, ruleset)
