# tests/test_golden_cases.py
import json
from pathlib import Path

from engine_ruleset import load_ruleset, suggest


def test_golden_cases():
    ruleset_path = Path("ruleset.v4.json")
    if not ruleset_path.exists():
        # fallback: permite rodar antes de gerar o v4
        ruleset_path = Path("ruleset.json")

    ruleset = load_ruleset(str(ruleset_path))
    cases = json.loads(Path("tests/golden_cases.json").read_text(encoding="utf-8"))

    failures = []
    for c in cases:
        s = suggest(c["text"], ruleset)
        if s.specialtyId != c["expected"]:
            failures.append((c["text"], c["expected"], s.specialtyId, s.score, s.why))

    assert not failures, "Falhas:\n" + "\n".join(
        f"- text={t!r} expected={e} got={g} score={sc} why={why}"
        for t, e, g, sc, why in failures
    )
