from engine_ruleset import load_ruleset, suggest_specialty


def test_synonym_cefaleia_maps_to_neuro():
    ruleset = load_ruleset("ruleset.v4.json")
    s = suggest_specialty("estou com cefaleia", ruleset)
    assert "Neuro" in s.specialty


def test_accent_insensitive_oftalmo():
    ruleset = load_ruleset("ruleset.v4.json")
    s = suggest_specialty("minha visao esta embacada", ruleset)
    assert "Oftalmo" in s.specialty


def test_generalist_penalty_dentista_wins():
    ruleset = load_ruleset("ruleset.v4.json")
    s = suggest_specialty("dor no dente e cansaco", ruleset)
    assert "Dentista" in s.specialty
