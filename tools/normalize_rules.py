from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


MERGE_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")

ID_SAFE = re.compile(r"[^a-z0-9_]+")


def die(msg: str, code: int = 1) -> None:
    print(f"[normalize_rules] ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def find_merge_markers(root: Path) -> List[Tuple[Path, int, str]]:
    """
    Detecta APENAS marcadores reais de conflito do Git:
      - linha começando com <<<<<<<
      - linha exatamente =======
      - linha começando com >>>>>>>
    Ignora venv, .git e caches.
    """
    EXCLUDE_DIR_PARTS = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "env31210",  # seu venv
        "build",
        "dist",
        ".pytest_cache",
    }

    hits: List[Tuple[Path, int, str]] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue

        # ignora qualquer arquivo dentro de diretórios excluídos
        if set(p.parts).intersection(EXCLUDE_DIR_PARTS):
            continue

        if p.suffix.lower() not in {".py", ".yaml", ".yml", ".md", ".txt", ".json"}:
            continue

        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for i, line in enumerate(text.splitlines(), start=1):
            s = line.strip()
            if s.startswith("<<<<<<<") or s.startswith(">>>>>>>") or s == "=======":
                hits.append((p, i, line.rstrip()))

    return hits



def slug_id(name: str) -> str:
    s = name.strip().lower()
    # troca acentos simples (não é “normalização semântica”; é só para id estável)
    s = (
        s.replace("á", "a").replace("à", "a").replace("ã", "a").replace("â", "a")
         .replace("é", "e").replace("ê", "e")
         .replace("í", "i")
         .replace("ó", "o").replace("ô", "o").replace("õ", "o")
         .replace("ú", "u")
         .replace("ç", "c")
    )
    s = s.replace("&", " and ")
    s = re.sub(r"[\s\-\/]+", "_", s)
    s = ID_SAFE.sub("", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x2 = x.strip()
        if not x2:
            continue
        if x2 not in seen:
            seen.add(x2)
            out.append(x2)
    return out


def ensure_list(obj: Any, field: str) -> List[str]:
    if obj is None:
        return []
    if not isinstance(obj, list):
        die(f"Campo '{field}' deve ser lista, veio: {type(obj).__name__}")
    return [str(x) for x in obj]


def load_yaml(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"Falha ao parsear YAML ({path}): {e}")
    if not isinstance(data, dict):
        die(f"YAML raiz deve ser um objeto/dict. Veio: {type(data).__name__}")
    return data


def normalize_rules(yaml_data: Dict[str, Any]) -> Dict[str, Any]:
    version = yaml_data.get("version")
    if not isinstance(version, int):
        die("Campo 'version' (int) é obrigatório.")

    locale = yaml_data.get("locale", "pt-BR")
    if not isinstance(locale, str):
        die("Campo 'locale' deve ser string.")

    scoring = yaml_data.get("scoring") or {}
    if not isinstance(scoring, dict):
        die("Campo 'scoring' deve ser objeto/dict.")
    # aceita nomes antigos do YAML (strong_weight/weak_weight) e mapeia
    strong_w = scoring.get("strongWeight", scoring.get("strong_weight", 2))
    weak_w = scoring.get("weakWeight", scoring.get("weak_weight", 1))
    min_score = scoring.get("minScore", scoring.get("min_score", 1))

    for k, v in [("strongWeight", strong_w), ("weakWeight", weak_w), ("minScore", min_score)]:
        if not isinstance(v, int) or v <= 0:
            die(f"scoring.{k} deve ser int > 0 (veio {v}).")

    fallback = yaml_data.get("fallback") or {}
    if not isinstance(fallback, dict):
        die("Campo 'fallback' deve ser objeto/dict.")
    # fallback pode ter 'name' (legado). Preferimos um ID estável.
    fallback_id = yaml_data.get("fallbackSpecialtyId")
    if fallback_id is None:
        fb_name = fallback.get("id") or fallback.get("name") or "clinical_medicine"
        fallback_id = slug_id(str(fb_name))

    specialties = yaml_data.get("specialties")
    if not isinstance(specialties, list) or not specialties:
        die("Campo 'specialties' deve ser uma lista não-vazia.")

    out_specialties: List[Dict[str, Any]] = []

    for idx, sp in enumerate(specialties):
        if not isinstance(sp, dict):
            die(f"specialties[{idx}] deve ser objeto/dict.")
        name = sp.get("displayName", sp.get("name"))
        if not isinstance(name, str) or not name.strip():
            die(f"specialties[{idx}] precisa de 'name' ou 'displayName'.")

        sp_id = sp.get("id")
        if sp_id is None:
            sp_id = slug_id(name)
        if not isinstance(sp_id, str) or not sp_id:
            die(f"specialties[{idx}].id inválido.")

        confidence = sp.get("confidence")
        if not isinstance(confidence, (int, float)) or not (0 <= float(confidence) <= 1):
            die(f"specialties[{idx}].confidence deve ser número entre 0 e 1.")

        # aceita nomes antigos strong_keywords/weak_keywords
        strong = ensure_list(sp.get("strong", sp.get("strong_keywords")), f"specialties[{idx}].strong")
        weak = ensure_list(sp.get("weak", sp.get("weak_keywords")), f"specialties[{idx}].weak")

        # remove legado 'keywords' se existir (ou incorpora em weak, se você quiser)
        # aqui: descartamos por padrão para reduzir ambiguidade
        strong = dedupe_keep_order(strong)
        weak = dedupe_keep_order(weak)

        # remove overlap: se está em strong, não fica em weak
        strong_set = set(strong)
        weak = [w for w in weak if w not in strong_set]

        generalist = sp.get("generalist", False)
        if not isinstance(generalist, bool):
            die(f"specialties[{idx}].generalist deve ser booleano.")

        out_specialties.append(
            {
                "id": sp_id,
                "displayName": name.strip(),
                "confidence": float(confidence),
                "generalist": generalist,
                "strong": strong,
                "weak": weak,
            }
        )

    ruleset = {
        "version": version,
        "locale": locale,
        "scoring": {"strongWeight": strong_w, "weakWeight": weak_w, "minScore": min_score},
        "fallbackSpecialtyId": fallback_id,
        "synonyms": yaml_data.get("synonyms", {}) or {},
        "specialties": out_specialties,
    }

    # valida synonyms
    if not isinstance(ruleset["synonyms"], dict):
        die("Campo 'synonyms' deve ser objeto/dict (ex.: { 'ansiedade': ['nervoso', ...] }).")

    return ruleset


def main() -> None:
    root = Path(".").resolve()
    markers = find_merge_markers(root)
    if markers:
        print("[normalize_rules] Encontrado(s) merge marker(s):", file=sys.stderr)
        for p, line, txt in markers[:200]:
            print(f" - {p}:{line} :: {txt}", file=sys.stderr)
        die("Resolva os merge markers antes de normalizar.", code=2)

    rules_yaml = Path(sys.argv[1] if len(sys.argv) > 1 else "rules.yaml")
    if not rules_yaml.exists():
        die(f"Arquivo não encontrado: {rules_yaml}")

    data = load_yaml(rules_yaml)
    ruleset = normalize_rules(data)

    out_json = Path(sys.argv[2] if len(sys.argv) > 2 else "ruleset.json")
    out_json.write_text(json.dumps(ruleset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[normalize_rules] OK: gerado {out_json} ({len(ruleset['specialties'])} especialidades).")


if __name__ == "__main__":
    main()
