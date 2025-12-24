import streamlit as st
from engine import load_rules, suggest_specialty

st.set_page_config(
    page_title="Health Care",
    page_icon="🩺",
    layout="centered",
    initial_sidebar_state="collapsed",
)

def _get_clear_flag() -> bool:
    # Compatível com st.query_params (novo) e experimental_get_query_params (antigo)
    try:
        val = st.query_params.get("clear")
        if isinstance(val, list):
            val = val[0] if val else None
        return str(val) == "1"
    except Exception:
        qp = st.experimental_get_query_params()
        return qp.get("clear", ["0"])[0] == "1"

def _clear_query_params():
    try:
        st.query_params.clear()
    except Exception:
        st.experimental_set_query_params()

# Estado
if "text" not in st.session_state:
    st.session_state["text"] = ""
if "last" not in st.session_state:
    st.session_state.last = None

# Se clicou no lixinho (?clear=1)
if _get_clear_flag():
    st.session_state["text"] = ""
    st.session_state.last = None
    _clear_query_params()
    st.rerun()

CSS = """
<style>
:root{
  /* Cozy Clinic — LIGHT */
  --bg:#fbf7f2;                /* warm off-white */
  --bg2:#f3f7ff;               /* soft blue */
  --panel: rgba(255,255,255,0.78);
  --stroke: rgba(28,35,48,0.10);
  --text: rgba(28,35,48,0.92);
  --muted: rgba(28,35,48,0.62);

  --primary:#ff6b6b;           /* coral */
  --mint:#4ecdc4;              /* mint */
  --sun:#f7c948;               /* warm yellow */
}

.stApp{
  background:
    radial-gradient(1200px 700px at 18% 10%, rgba(247,201,72,0.28), transparent 60%),
    radial-gradient(900px 520px at 82% 18%, rgba(78,205,196,0.20), transparent 60%),
    linear-gradient(180deg, var(--bg), var(--bg2));
  color: var(--text);
}

/* remove decoração e header default */
div[data-testid="stDecoration"]{display:none;}
header {visibility:hidden; height:0px;}
.block-container{padding-top:5.2rem; padding-bottom:2.2rem; max-width:760px;}

/* AppBar */
.appbar{
  position:fixed; top:0; left:0; right:0; height:64px; z-index:999;
  display:flex; align-items:center; justify-content:center;
  backdrop-filter: blur(10px);
  background: rgba(255,255,255,0.72);
  border-bottom: 1px solid var(--stroke);
}
.appbar-inner{
  width:min(760px, calc(100% - 32px));
  display:flex; align-items:center; justify-content:center;
  position:relative;
}
.brand{display:flex; gap:10px; align-items:center; font-weight:900; font-size:20px; color: var(--text);}
.dot{
  width:10px; height:10px; border-radius:999px; background: var(--sun);
  box-shadow: 0 0 18px rgba(247,201,72,0.45);
}
.sub{
  text-align:center;
  color: var(--muted);
  margin: 10px 0 14px 0;
  font-size: 14px;
}

/* Form vira o “InputCard” */
div[data-testid="stForm"]{
  position: relative; /* permite posicionar o lixinho dentro */
  background: var(--panel);
  border: 1px solid var(--stroke);
  border-radius: 18px;
  padding: 18px;
  box-shadow: 0 18px 40px rgba(0,0,0,0.10);
}

/* Lixinho dentro do box (link) */
a.trash{
  position:absolute;
  top:14px;
  right:14px;
  width:42px;
  height:42px;
  display:flex;
  align-items:center;
  justify-content:center;
  border-radius:14px;
  background: rgba(28,35,48,0.05);
  border: 1px solid rgba(28,35,48,0.10);
  text-decoration:none;
  transition: transform .08s ease, background .2s ease;
  user-select:none;
}
a.trash:hover{ background: rgba(28,35,48,0.08); transform: translateY(-1px); }

/* Textarea */
div[data-baseweb="textarea"] textarea{
  border-radius: 14px !important;
  background: rgba(255,255,255,0.90) !important;
  border: 1px solid rgba(28,35,48,0.12) !important;
  color: rgba(28,35,48,0.92) !important;
}
div[data-baseweb="textarea"] textarea::placeholder{
  color: rgba(28,35,48,0.45) !important;
}

/* Buttons */
div.stButton > button, div.stForm button{
  border-radius: 14px !important;
  padding: 10px 14px !important;
  border: 1px solid rgba(28,35,48,0.12) !important;
}
button[kind="primary"]{
  background: linear-gradient(135deg, var(--primary), #ff8e8e) !important;
  border: none !important;
  box-shadow: 0 16px 30px rgba(255,107,107,0.22);
  font-weight: 900 !important;
  color: white !important;
}

/* Result card */
.result-card{
  margin-top: 14px;
  background: rgba(255,255,255,0.82);
  border: 1px solid rgba(255,107,107,0.22);
  border-radius: 18px;
  padding: 18px;
  box-shadow: 0 18px 40px rgba(0,0,0,0.10);
}
.pill{
  display:inline-flex; align-items:center; gap:8px;
  border-radius:999px; padding:6px 10px;
  border:1px solid rgba(28,35,48,0.12);
  background: rgba(28,35,48,0.04);
  color: rgba(28,35,48,0.72);
  font-size: 12px;
}
.h1{ font-size: 22px; font-weight: 900; margin: 0; color: rgba(28,35,48,0.92); }
.muted{ color: var(--muted); }
hr{ border:none; border-top:1px solid rgba(28,35,48,0.10); margin: 12px 0; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# AppBar
st.markdown(
    """
    <div class="appbar">
      <div class="appbar-inner">
        <div class="brand">
          <span style="font-size:22px;">🩺</span>
          <span>Health Care</span>
          <span class="dot"></span>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="sub">Sugestão de especialidade com base em texto (sem diagnóstico / sem prescrição).</div>',
    unsafe_allow_html=True,
)

st.markdown("### Descreva (de forma genérica) o que você quer entender")

with st.form("triage_form", clear_on_submit=False):
    # lixinho dentro do box (link)
    st.markdown('<a class="trash" href="?clear=1" title="Limpar">🗑️</a>', unsafe_allow_html=True)

    st.text_area(
        label="",
        key="text",
        placeholder="Ex: tenho dor no dente… / estou acima do peso… / estou com ansiedade…",
        height=140,
        label_visibility="collapsed",
    )



    # CTA centralizado
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        submit = st.form_submit_button("Sugerir especialidade", type="primary", use_container_width=True)

if submit:
    user_text = st.session_state.get("text", "").strip()
    if not user_text:
        st.warning("Escreva um texto (genérico) para eu sugerir uma especialidade.")
    else:
        rules = load_rules("rules.yaml")  # <- era ruleset.v5.json
        st.session_state.last = suggest_specialty(user_text, rules)

if st.session_state.last is not None:
    s = st.session_state.last
    termos = ", ".join(s.matched_keywords) if s.matched_keywords else "Nenhum termo específico detectado (porta de entrada)."

    st.markdown(
        f"""
        <div class="result-card">
          <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
            <p class="h1">{s.specialty}</p>
            <span class="pill">✨ Confiança (heurística): <b>{int(s.confidence * 100)}%</b></span>
          </div>
          <p class="muted" style="margin-top:6px;"><b>Termos:</b> {termos}</p>
          <hr/>
          <p><b>Por quê:</b> {s.why}</p>
          <p><b>Próximo passo:</b> {s.next_step}</p>
          <hr/>
          <p class="muted">{s.disclaimer}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.caption('Dica: frases curtas com 1–2 sintomas (ex: “dor no dente”, “palpitação”, “coceira na pele”).')
