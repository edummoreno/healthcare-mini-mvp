# engine_ruleset.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional
import json
import re
import unicodedata


DISCLAIMER_DEFAULT = (
    "Este app sugere uma especialidade com base no texto informado. "
    "Não realiza diagnóstico, não prescreve e não define urgência."
)


def normalize_text(s: str) -> str:
    """
    Normalização em 3 passos:
      1) lower/trim/colapsar espaços
      2) remover acentos/diacríticos
      3) normalizar pontuação/hífen/barra para espaços (mantém só [a-z0-9 ])
    """
    if not s:
        return ""
    s = s.lower().strip()

    # 2) remove diacríticos
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))

    # 3) troca tudo que não for letra/dígito por espaço
    s = re.sub(r"[^a-z0-9]+", " ", s)

    # 1) colapsa espaços
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _kw_matches(text_norm: str, kw_norm: str) -> bool:
    if not kw_norm:
        return False
    if " " in kw_norm:
        return kw_norm in text_norm
    # palavra única: boundary
    return re.search(rf"\b{re.escape(kw_norm)}\b", text_norm) is not None


def build_synonyms_map(synonyms_raw: Dict[str, List[str]]) -> Dict[str, List[Tuple[str, str]]]:
    """
    Retorna: canonical_norm -> [(variant_norm, variant_original), ...]
    """
    out: Dict[str, List[Tuple[str, str]]] = {}
    for canonical, variants in (synonyms_raw or {}).items():
        c_norm = normalize_text(canonical)
        if not c_norm:
            continue
        bucket: List[Tuple[str, str]] = []
        for v in variants or []:
            v_norm = normalize_text(v)
            if not v_norm or v_norm == c_norm:
                continue
            bucket.append((v_norm, v))
        # dedupe por norm
        seen = set()
        uniq: List[Tuple[str, str]] = []
        for v_norm, v_orig in bucket:
            if v_norm in seen:
                continue
            seen.add(v_norm)
            uniq.append((v_norm, v_orig))
        out[c_norm] = uniq
    return out


def kw_matches_with_synonyms(
    text_norm: str,
    kw_norm: str,
    syn_map: Dict[str, List[Tuple[str, str]]],
) -> Tuple[bool, Optional[str]]:
    """
    Retorna (matched, matched_variant_original_or_none)
    """
    if _kw_matches(text_norm, kw_norm):
        return True, None
    for v_norm, v_orig in syn_map.get(kw_norm, []):
        if _kw_matches(text_norm, v_norm):
            return True, v_orig
    return False, None


@dataclass(frozen=True)
class Suggestion:
    specialtyId: str
    specialtyName: str
    score: int
    strongHits: List[str]
    weakHits: List[str]
    why: str
    disclaimer: str


def load_ruleset(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def suggest(text: str, ruleset: Dict[str, Any]) -> Suggestion:
    text_norm = normalize_text(text)

    scoring = ruleset.get("scoring", {})
    strong_w = int(scoring.get("strongWeight", 2))
    weak_w = int(scoring.get("weakWeight", 1))
    min_score = int(scoring.get("minScore", 1))

    fallback_id = ruleset.get("fallbackSpecialtyId", "clinica_medica")
    syn_map = build_synonyms_map(ruleset.get("synonyms", {}))

    best: Optional[Dict[str, Any]] = None
    best_score = -1
    best_strong = -1
    best_conf = -1.0
    best_hits: Tuple[List[str], List[str]] = ([], [])

    runner_up: Optional[Tuple[Dict[str, Any], int, int, float, Tuple[List[str], List[str]]]] = None

    for sp in ruleset.get("specialties", []):
        strong_hits: List[str] = []
        weak_hits: List[str] = []

        # strong
        for kw in sp.get("strong", []):
            kw_norm = normalize_text(kw)
            matched, via_syn = kw_matches_with_synonyms(text_norm, kw_norm, syn_map)
            if matched:
                strong_hits.append(kw if via_syn is None else f"{kw} (sin.: {via_syn})")

        # weak
        for kw in sp.get("weak", []):
            kw_norm = normalize_text(kw)
            matched, via_syn = kw_matches_with_synonyms(text_norm, kw_norm, syn_map)
            if matched:
                weak_hits.append(kw if via_syn is None else f"{kw} (sin.: {via_syn})")

        score = strong_w * len(strong_hits) + weak_w * len(weak_hits)
        if score < min_score:
            continue

        conf = float(sp.get("confidence", 0.0))
        strong_count = len(strong_hits)

        # ranking
        is_better = (
            (score > best_score)
            or (score == best_score and strong_count > best_strong)
            or (score == best_score and strong_count == best_strong and conf > best_conf)
        )
        if is_better:
            # salva runner-up anterior
            if best is not None:
                runner_up = (best, best_score, best_strong, best_conf, best_hits)

            best = sp
            best_score = score
            best_strong = strong_count
            best_conf = conf
            best_hits = (strong_hits, weak_hits)
        else:
            # atualiza runner-up
            if runner_up is None:
                runner_up = (sp, score, strong_count, conf, (strong_hits, weak_hits))
            else:
                ru_sp, ru_score, ru_strong, ru_conf, ru_hits = runner_up
                ru_better = (
                    (score > ru_score)
                    or (score == ru_score and strong_count > ru_strong)
                    or (score == ru_score and strong_count == ru_strong and conf > ru_conf)
                )
                if ru_better:
                    runner_up = (sp, score, strong_count, conf, (strong_hits, weak_hits))

    # fallback se nada bateu
    if best is None:
        fb = next((s for s in ruleset.get("specialties", []) if s.get("id") == fallback_id), None)
        if fb is None:
            fb = {"id": fallback_id, "displayName": "Clínica Médica"}
        return Suggestion(
            specialtyId=fb["id"],
            specialtyName=fb.get("displayName", fb["id"]),
            score=0,
            strongHits=[],
            weakHits=[],
            why="Não encontrei termos específicos suficientes; sugerindo uma opção mais geral.",
            disclaimer=DISCLAIMER_DEFAULT,
        )

    # (opcional já preparando Upgrade 2) “penaliza generalista” se houver runner-up próximo
    if best.get("generalist") is True and runner_up is not None:
        ru_sp, ru_score, _, _, ru_hits = runner_up
        # se runner-up estiver “perto”, prefere o mais específico
        if ru_score >= best_score - 1 and ru_score > 0:
            best = ru_sp
            best_score = ru_score
            best_hits = ru_hits

    strong_hits, weak_hits = best_hits
    why_parts = []
    if strong_hits:
        why_parts.append(f"Sinais fortes: {', '.join(strong_hits[:6])}")
    if weak_hits:
        why_parts.append(f"Sinais fracos: {', '.join(weak_hits[:6])}")
    why = " | ".join(why_parts) if why_parts else "Termos relacionados encontrados no texto."

    return Suggestion(
        specialtyId=best["id"],
        specialtyName=best.get("displayName", best["id"]),
        score=best_score,
        strongHits=strong_hits,
        weakHits=weak_hits,
        why=why,
        disclaimer=DISCLAIMER_DEFAULT,
    )
