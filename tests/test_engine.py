from engine import load_rules, suggest_specialty


def test_fallback_when_no_match():
    rules = load_rules("rules.yaml")
    s = suggest_specialty("texto aleatório sem relação", rules)
    assert s.specialty  # existe
    assert s.confidence > 0


def test_match_cardiologia():
    rules = load_rules("rules.yaml")
    s = suggest_specialty("tenho dor no peito e palpitação", rules)
    assert s.specialty == "Cardiologia"
    assert len(s.matched_keywords) >= 1
