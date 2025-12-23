import streamlit as st
from engine import load_rules, suggest_specialty

st.set_page_config(page_title="Health Care — Mini MVP", page_icon="🩺", layout="centered")

st.title("🩺 Health Care — Mini MVP")
st.caption("Sugestão de especialidade com base em texto (sem diagnóstico / sem prescrição).")

with st.expander("Privacidade por padrão"):
    st.write(
        "- Este app **não salva** o texto digitado.\n"
        "- Evite inserir dados pessoais identificáveis.\n"
        "- Use exemplos genéricos/anônimos durante testes."
    )

text = st.text_area(
    "Descreva (de forma genérica) o que você quer organizar/entender:",
    placeholder="Ex: tenho dor no peito e palpitação há alguns dias...",
    height=140,
)

col1, col2 = st.columns([1, 1])
with col1:
    run = st.button("Sugerir especialidade", type="primary")
with col2:
    st.button("Limpar", on_click=lambda: st.session_state.update({"_clear": True}))

if st.session_state.get("_clear"):
    st.session_state["_clear"] = False
    st.rerun()

if run:
    if not text.strip():
        st.warning("Escreva um texto (genérico) para eu sugerir uma especialidade.")
    else:
        rules = load_rules("rules.yaml")
        s = suggest_specialty(text, rules)

        st.subheader(f"Sugestão: **{s.specialty}**")
        st.write(f"Confiança (heurística): **{int(s.confidence * 100)}%**")

        if s.matched_keywords:
            st.write("✅ Termos encontrados:")
            st.write(", ".join(s.matched_keywords))
        else:
            st.write("ℹ️ Não encontrei termos fortes; usei sugestão de porta de entrada.")

        st.write("**Por quê:**", s.why)
        st.write("**Próximo passo sugerido:**", s.next_step)

        st.info(s.disclaimer)
