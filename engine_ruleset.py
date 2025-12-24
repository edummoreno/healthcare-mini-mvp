from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


@dataclass(frozen=True)
class Suggestion:
    specialtyId: str
    specialtyName: str
    specialty: str
    confidence: float
    matched_keywords: List[str]
    strongHits: List[str]
    weakHits: List[str]
    score: int
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
        kw_tokens = [p for p in kw_norm.split(" ") if p]
        if not kw_tokens:
            return False

        # tenta substring direta
        if kw_norm in text_norm:
            return True

        # tenta subsequência de tokens (permite palavras intermediárias, mantendo ordem)
        text_tokens = text_norm.split(" ")
        idx = 0
        for kw in kw_tokens:
            try:
                idx = text_tokens.index(kw, idx) + 1
            except ValueError:
                return False
        return True
    # palavra única -> boundary
    return re.search(r"\b" + re.escape(kw_norm) + r"\b", text_norm) is not None


def _slugify(text: str) -> str:
    text = _normalize(text)
    return re.sub(r"\s+", "_", text)


def _normalize_ruleset_structure(ruleset: Dict[str, Any]) -> Dict[str, Any]:
    # normaliza nomenclatura entre YAML (snake_case) e JSON (camelCase)
    scoring = ruleset.get("scoring") or {}
    scoring = {
        "strongWeight": scoring.get("strongWeight", scoring.get("strong_weight", 2)),
        "weakWeight": scoring.get("weakWeight", scoring.get("weak_weight", 1)),
        "minScore": scoring.get("minScore", scoring.get("min_score", 1)),
        "topK": scoring.get("topK", scoring.get("top_k", 3)),
    }

    specialties = []
    for spec in ruleset.get("specialties") or []:
        name = spec.get("displayName") or spec.get("name") or ""
        spec_id = spec.get("id") or _slugify(name)
        specialties.append(
            {
                "id": spec_id,
                "displayName": name,
                "confidence": spec.get("confidence", 0.6),
                "generalist": bool(spec.get("generalist", False)),
                "strong": spec.get("strong") or spec.get("strong_keywords") or [],
                "weak": spec.get("weak") or spec.get("weak_keywords") or [],
                "why": spec.get("why", spec.get("confidence_reason", "Correspondência por palavras-chave.")),
                "next_step": spec.get("next_step", "Busque uma avaliação com um(a) profissional de saúde."),
            }
        )

    return {
        "version": ruleset.get("version", 4),
        "locale": ruleset.get("locale", "pt-BR"),
        "scoring": scoring,
        "fallbackSpecialtyId": ruleset.get("fallbackSpecialtyId", ruleset.get("fallback_specialty_id", "clinica_medica")),
        "synonyms": ruleset.get("synonyms") or {},
        "specialties": specialties,
        "disclaimer": ruleset.get(
            "disclaimer",
            "⚠️ Importante: isto NÃO é diagnóstico, NÃO é prescrição e NÃO define urgência. "
            "É apenas uma sugestão de especialidade para orientar o próximo passo.",
        ),
    }


def load_ruleset(path: str = "ruleset.v4.json") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)

    if p.suffix.lower() in {".yml", ".yaml"}:
        with open(p, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f) or {}

    return _normalize_ruleset_structure(raw)


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


def _confidence_from_score(base_conf: float, score: int) -> float:
    return min(0.95, float(base_conf) + 0.02 * max(0, int(score) - 1))


def suggest(user_text: str, ruleset: Dict[str, Any]) -> Suggestion:
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

    candidates: List[Tuple[int, int, float, Dict[str, Any], List[str], List[str], List[str]]] = []

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

        candidates.append(
            (weighted_score, len(strong_hits), base_conf, spec, strong_hits + weak_hits, strong_hits, weak_hits)
        )

    if not candidates:
        fb_id = ruleset.get("fallbackSpecialtyId", "clinica_medica")
        fb_name = "Clínica Médica"
        for s in ruleset.get("specialties") or []:
            if s.get("id") == fb_id:
                fb_name = s.get("displayName", fb_name)
                break

        return Suggestion(
            specialtyId=fb_id,
            specialtyName=fb_name,
            specialty=fb_name,
            confidence=0.55,
            matched_keywords=[],
            strongHits=[],
            weakHits=[],
            score=0,
            why="Sugestão padrão (sem correspondência forte suficiente).",
            next_step="Busque uma avaliação com um(a) profissional de saúde.",
            disclaimer=disclaimer,
            alternatives=[],
        )

    has_clear_specific = any(sc > 0 and not bool(spec.get("generalist", False)) for (_, sc, _, spec, _, _, _) in candidates)
    if has_clear_specific:
        candidates = [c for c in candidates if not bool(c[3].get("generalist", False))]

    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    top = candidates[: max(1, top_k)]
    weighted_score, strong_count, base_conf, spec, matched, strong_hits, weak_hits = top[0]
    confidence = _confidence_from_score(base_conf, weighted_score)

    why = spec.get("why", "Correspondência por palavras-chave.")
    why = f"{why} (fortes={strong_count}, score={weighted_score})"
    if syn_hits:
        why += " | sinônimos: " + ", ".join([f"{v}→{c}" for (v, c) in syn_hits])

    next_step = spec.get("next_step", "Busque uma avaliação com um(a) profissional de saúde.")

    alternatives: List[Dict[str, Any]] = []
    for (ws, sc, bc, s, m, sh, wh) in top[1:]:
        alternatives.append(
            {
                "specialty": s.get("displayName", ""),
                "confidence": float(bc),
                "score": int(ws),
                "strong_hits": int(sc),
                "matched": m,
                "strong": sh,
                "weak": wh,
            }
        )

    specialty_name = spec.get("displayName", "Clínica Médica")
    spec_id = spec.get("id", _slugify(specialty_name))

    return Suggestion(
        specialtyId=spec_id,
        specialtyName=specialty_name,
        specialty=specialty_name,
        confidence=confidence,
        matched_keywords=matched,
        strongHits=strong_hits,
        weakHits=weak_hits,
        score=int(weighted_score),
        why=why,
        next_step=next_step,
        disclaimer=disclaimer,
        alternatives=alternatives,
    )


def suggest_specialty(user_text: str, ruleset: Dict[str, Any]) -> Suggestion:
    return suggest(user_text, ruleset)
