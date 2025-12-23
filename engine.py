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
<<<<<<< HEAD
=======
    # Normalização simples (sem remover acentos pra manter PT-BR direto).
    # Se quiser evoluir: unidecode.
>>>>>>> 847ab09fe56758bb3a31b4f230420f274ea5fa2d
    text = re.sub(r"\s+", " ", text)
    return text


<<<<<<< HEAD
def _kw_matches(text_norm: str, kw_norm: str) -> bool:
    """
    Match simples e explicável, com um pouco menos de falso-positivo:
    - Se keyword tem espaço/hífen/número, usa substring normalizada.
    - Se keyword é "uma palavra", usa boundary (\b) pra evitar pegar dentro de outras palavras.
    """
    if not kw_norm:
        return False

    # Se tiver espaço ou hífen, substring funciona melhor.
    if " " in kw_norm or "-" in kw_norm or "/" in kw_norm:
        return kw_norm in text_norm

    # Word-boundary para evitar: "rim" casar com "primario"
    # Obs: \b funciona ok com unicode na maioria dos casos.
    pattern = r"\b" + re.escape(kw_norm) + r"\b"
    return re.search(pattern, text_norm) is not None


=======
>>>>>>> 847ab09fe56758bb3a31b4f230420f274ea5fa2d
def load_rules(path: str = "rules.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def suggest_specialty(user_text: str, rules: Dict[str, Any]) -> Suggestion:
    text = _normalize(user_text)

<<<<<<< HEAD
    scoring = rules.get("scoring", {}) or {}
    strong_w = int(scoring.get("strong_weight", 2))
    weak_w = int(scoring.get("weak_weight", 1))

    # best tuple:
    # (weighted_score, strong_hits_count, base_conf, spec, matched_list)
    best: Tuple[int, int, float, Dict[str, Any], List[str]] | None = None

    for spec in rules.get("specialties", []):
        base_conf = float(spec.get("confidence", 0.6))

        strong_hits: List[str] = []
        weak_hits: List[str] = []

        # Novo formato
        for kw in spec.get("strong_keywords", []) or []:
            nkw = _normalize(str(kw))
            if _kw_matches(text, nkw):
                strong_hits.append(str(kw))

        for kw in spec.get("weak_keywords", []) or []:
            nkw = _normalize(str(kw))
            if _kw_matches(text, nkw):
                weak_hits.append(str(kw))

        # Compatibilidade: se o YAML antigo usa só "keywords"
        legacy_hits: List[str] = []
        for kw in spec.get("keywords", []) or []:
            kw_str = str(kw)
            nkw = _normalize(kw_str)
            if _kw_matches(text, nkw):
                legacy_hits.append(kw_str)

        # Evita contar duplicado se keywords == união de strong/weak
        strong_set = set(strong_hits)
        weak_set = set(weak_hits)
        legacy_hits = [k for k in legacy_hits if k not in strong_set and k not in weak_set]

        # Se não tem strong/weak definidos, trate legacy como "weak"
        has_explicit_buckets = bool(spec.get("strong_keywords") or spec.get("weak_keywords"))
        if not has_explicit_buckets:
            weak_hits.extend(legacy_hits)
            legacy_hits = []

        weighted_score = strong_w * len(strong_hits) + weak_w * len(weak_hits) + weak_w * len(legacy_hits)
        matched = strong_hits + weak_hits + legacy_hits

        if weighted_score <= 0:
            continue

        candidate = (weighted_score, len(strong_hits), base_conf, spec, matched)

        # Tie-break:
        # 1) maior score ponderado
        # 2) mais strong hits
        # 3) maior confidence base
        if best is None or candidate[:3] > best[:3]:
            best = candidate

    disclaimer = rules.get(
        "disclaimer",
        "⚠️ Importante: isto NÃO é diagnóstico, NÃO é prescrição e NÃO define urgência. "
        "É apenas uma sugestão de especialidade para orientar o próximo passo.",
    )

    # fallback se nada casou
    if best is None:
        fb = rules.get("fallback", {}) or {}
=======
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
>>>>>>> 847ab09fe56758bb3a31b4f230420f274ea5fa2d
        return Suggestion(
            specialty=fb.get("name", "Clínica Médica"),
            confidence=float(fb.get("confidence", 0.5)),
            matched_keywords=[],
            why=fb.get("why", "Sugestão padrão."),
            next_step=fb.get("next_step", "Busque uma avaliação com um(a) profissional de saúde."),
            disclaimer=disclaimer,
        )

<<<<<<< HEAD
    weighted_score, strong_count, base_conf, spec, matched = best

    # Confiança: base + bônus pequeno por evidência (ponderada), com teto
    # (mantém explicável e evita explodir)
    confidence = min(0.95, base_conf + 0.02 * max(0, weighted_score - 1))

    why = (
        spec.get("why")
        or spec.get("confidence_reason")
        or "Correspondência por palavras-chave."
    )

    # Opcional: deixa o "por quê" mais claro pro usuário (explicável)
    why = f"{why} (fortes={strong_count}, score={weighted_score})"

    next_step = spec.get("next_step", "Busque uma avaliação com um(a) profissional de saúde.")
=======
    _, spec, matches = best

    # Confiança pode subir um pouco com mais matches (simples e explicável)
    base_conf = float(spec.get("confidence", 0.6))
    confidence = min(0.95, base_conf + 0.05 * max(0, len(matches) - 1))
>>>>>>> 847ab09fe56758bb3a31b4f230420f274ea5fa2d

    return Suggestion(
        specialty=spec.get("name", "Clínica Médica"),
        confidence=confidence,
<<<<<<< HEAD
        matched_keywords=matched,
        why=why,
        next_step=next_step,
=======
        matched_keywords=matches,
        why=spec.get("why", "Correspondência por palavras-chave."),
        next_step=spec.get("next_step", "Busque uma avaliação com um(a) profissional de saúde."),
>>>>>>> 847ab09fe56758bb3a31b4f230420f274ea5fa2d
        disclaimer=disclaimer,
    )
