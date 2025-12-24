from __future__ import annotations

import argparse
from pathlib import Path
import yaml


# Extras "semânticos" (sinônimos/frases comuns) para melhorar recall.
# Você pode ir ajustando com base nos seus testes reais.
EXTRA = {
    "Odontologia (Dentista)": {
        "strong": ["dente doendo", "dor de dente forte", "siso", "siso inflamado", "gengiva sangrando"],
        "weak": ["sensibilidade ao frio", "sensibilidade ao quente", "dor ao mastigar"],
    },
    "Oftalmologia": {
        "strong": ["vista embaçada", "visao turva", "não enxergo direito", "nao enxergo direito", "terçol", "tercol"],
        "weak": ["vista cansada", "olhos cansados", "ardência no olho", "ardencia no olho"],
    },
    "Obstetrícia": {
        "strong": ["teste de gravidez positivo", "suspeita de gravidez", "estou grávida", "estou gravida", "sangramento na gravidez"],
        "weak": ["dor na barriga na gravidez", "dor abdominal na gravidez"],
    },
    "Ginecologia e Obstetrícia": {
        "strong": ["coceira vaginal", "dor na relação", "dor na relacao", "corrimento com cheiro", "sangramento fora do ciclo"],
        "weak": ["seca vaginal", "diminuição da libido", "diminuicao da libido"],
    },
    "Otorrinolaringologia": {
        "strong": ["perda de audição", "perda de audicao", "nariz sangrando", "sangramento nasal"],
        "weak": ["nariz entupido", "dor facial", "pressão no rosto", "pressao no rosto"],
    },
    "Urologia": {
        "strong": ["urina com sangue", "dificuldade para urinar", "infecção urinária recorrente", "infeccao urinaria recorrente"],
        "weak": ["acordo para urinar", "acordo a noite para urinar", "dor lombar"],
    },
    "Reprodução Humana": {
        "strong": ["tentando ter filho", "tentando ter bebê", "tentando ter bebe", "tratamento de fertilidade"],
        "weak": ["dificuldade para engravidar", "ciclo irregular"],
    },
    "Mastologia": {
        "strong": ["caroço no seio", "caroco no seio", "secreção no seio", "secrecao no seio"],
        "weak": ["sensibilidade na mama", "incômodo na mama", "incomodo na mama"],
    },
    "Cardiologia": {
        "strong": ["aperto no peito", "pressão no peito", "pressao no peito", "coração acelerado", "coracao acelerado"],
        "weak": ["cansaço aos esforços", "cansaco aos esforcos", "tontura ao levantar"],
    },
    "Cirurgia Plástica": {
        "strong": ["prótese de silicone", "protese de silicone", "implante de silicone", "redução de mama", "reducao de mama"],
        "weak": ["procedimento estético", "procedimento estetico"],
    },
    "Ortopedia e Traumatologia": {
        "strong": ["dor no ombro", "dor no quadril", "torci o tornozelo", "torci o pé", "torci o pe"],
        "weak": ["dor ao caminhar", "dor ao subir escadas"],
    },
    "Neurologia": {
        "strong": ["avc", "derrame", "perdi a força", "perdi a forca", "formigamento nas mãos", "formigamento nas maos"],
        "weak": ["confusão mental", "confusao mental", "esquecimento"],
    },
    "Endocrinologia e Metabologia": {
        "strong": ["acima do peso", "sobrepeso", "obesidade", "quero emagrecer", "dificuldade para emagrecer"],
        "weak": ["muita fome", "fome excessiva", "compulsão alimentar", "compulsao alimentar"],
    },
    "Dermatologia": {
        "strong": ["dermatite", "eczema", "psoríase", "psoriase", "pele descamando"],
        "weak": ["pele irritada", "rash", "brotoeja"],
    },
    "Psiquiatria": {
        "strong": ["cansaço mental", "cansaco mental", "esgotamento", "burnout", "exaustão mental", "exaustao mental"],
        "weak": ["desânimo", "desanimo", "sem energia", "sobrecarga"],
    },
    "Gastroenterologia": {
        "strong": ["dor no estômago", "dor no estomago", "intolerância alimentar", "intolerancia alimentar"],
        "weak": ["má digestão", "ma digestao", "empachamento"],
    },
    "Pneumologia": {
        "strong": ["falta de ar ao esforço", "falta de ar aos esforços", "chiado ao respirar"],
        "weak": ["tosse com catarro", "catarro", "aperto no peito"],
    },
    "Alergia e Imunologia": {
        "strong": ["alergia alimentar", "rinite", "asma alérgica", "asma alergica"],
        "weak": ["espirro", "nariz coçando", "nariz cocando"],
    },
    "Reumatologia": {
        "strong": ["dor nas juntas", "juntas inchadas", "inflamação nas juntas", "inflamacao nas juntas"],
        "weak": ["dor no corpo inteiro", "dor generalizada"],
    },
    "Infectologia": {
        "strong": ["covid", "covid-19", "infecção de repetição", "infeccao de repeticao"],
        "weak": ["febre que não passa", "febre que nao passa"],
    },
    "Nutrologia": {
        "strong": ["reeducação alimentar", "reeducacao alimentar", "avaliação nutricional", "avaliacao nutricional"],
        "weak": ["quero emagrecer", "ganhar massa", "perder gordura"],
    },
    "Medicina do Sono": {
        "strong": ["não consigo dormir", "nao consigo dormir", "acordo várias vezes", "acordo varias vezes"],
        "weak": ["sono leve", "sono ruim"],
    },
    # (As demais você pode ir enriquecendo conforme os testes.)
}


MERGE_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def uniq_extend(lst: list[str], items: list[str]) -> None:
    seen = {str(x) for x in lst}
    for it in items:
        s = str(it)
        if s not in seen:
            lst.append(s)
            seen.add(s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Arquivo YAML de entrada (ex: rules.yaml)")
    ap.add_argument("--output", default="rules.cleaned.yaml", help="Arquivo YAML de saída")
    ap.add_argument(
        "--keep-empty-keywords",
        action="store_true",
        help="Em vez de remover a chave 'keywords', deixa como keywords: []",
    )
    args = ap.parse_args()

    in_path = Path(args.input)
    raw = in_path.read_text(encoding="utf-8")

    if any(m in raw for m in MERGE_MARKERS):
        raise SystemExit(
            "ERRO: seu YAML ainda tem marcadores de merge (<<<<<<< ======= >>>>>>>). Remova isso antes."
        )

    data = yaml.safe_load(raw) or {}
    specs = data.get("specialties") or []
    if not isinstance(specs, list):
        raise SystemExit("ERRO: 'specialties' precisa ser uma lista.")

    for spec in specs:
        if not isinstance(spec, dict):
            continue

        name = str(spec.get("name", "")).strip()

        # Garante listas
        spec.setdefault("strong_keywords", [])
        spec.setdefault("weak_keywords", [])
        if spec["strong_keywords"] is None:
            spec["strong_keywords"] = []
        if spec["weak_keywords"] is None:
            spec["weak_keywords"] = []

        # Remove / zera legacy keywords
        if args.keep_empty_keywords:
            spec["keywords"] = []
        else:
            spec.pop("keywords", None)

        # Enriquecimento semântico
        extra = EXTRA.get(name)
        if extra:
            uniq_extend(spec["strong_keywords"], extra.get("strong", []))
            uniq_extend(spec["weak_keywords"], extra.get("weak", []))

    out_path = Path(args.output)
    out_path.write_text(
        yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        ),
        encoding="utf-8",
    )

    print(f"OK: gerado {out_path}")


if __name__ == "__main__":
    main()
