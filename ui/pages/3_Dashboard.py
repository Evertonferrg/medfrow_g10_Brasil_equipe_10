import base64
import json
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="MediFlow HealthTech - Dashboard",
    page_icon="🩺",
    layout="wide",
)

RAIZ = Path(__file__).resolve().parents[1]
CAMINHO_LOGO = RAIZ / "assets" / "logo.png"
CAMINHO_EXAME = RAIZ / "assets" / "exame_torax.png"

# ------------------------------------------------------------------
# DADOS (hoje estáticos; depois basta preencher com o retorno da API)
# ------------------------------------------------------------------
DADOS = {
    "status_upload": "Processado",
    "documento": {
        "hospital": "HOSPITAL SANTA LUCIA",
        "titulo": "LAUDO DE EXAME RADIOLOGICO",
        "paciente": "Carlos Eduardo Mendes, 52 anos",
        "solicitante": "Dra. Renata Silveira CRM-SP 145892",
        "exame": "Tomografia de Tórax com contraste",
        "conclusao": "Quadro compatível com Tromboembolismo Pulmonar Agudo. "
        "Sugere-se correlação clínica urgente.",
        "imagem": CAMINHO_EXAME,
    },
    "paciente": {"nome": "Carlos Eduardo Mendes", "idade": 52},
    "clinico": {
        "urgencia": "URGENTE",
        "medico": "Dra. Renata Silveira",
        "crm": "145892-SP",
        "exame": "Tomografia de Tórax com contraste",
        "diagnostico": "Tromboembolismo Pulmonar Agudo (TEP)",
        "cid": "I26.9",
        "badges": [
            ("URGENTE", "red"),
            ("TEP Agudo", "blue"),
            ("Alta Gravidade", "orange"),
        ],
    },
    "payload": {
        "status": "processado",
        "documento_id": "DOC-CLIN-2026-8942",
        "classificacao": {
            "tipo_documento": "Laudo de Exame de Imagem",
            "nivel_prioridade": "Urgente",
            "score_confianca_classificacao": 0.99,
        },
        "dados_extraidos": {
            "paciente": {"nome": "Carlos Eduardo Mendes", "idade": 52},
            "diagnostico_principal": "Tromboembolismo Pulmonar Agudo (TEP)",
        },
    },
}

# Altura da área interna do preview e do JSON (ajuste fino do alinhamento)
# Se o card da esquerda terminar mais acima que o da direita, aumente ALTURA_PREVIEW.
ALTURA_PREVIEW = 745
ALTURA_JSON = 340

# ------------------------------------------------------------------
# ESTILO (as cores herdam do tema ativo do Streamlit: claro ou escuro)
# ------------------------------------------------------------------
st.markdown(
    """
<style>
    [data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 5rem; max-width: 1400px; }

    [data-testid="stLogo"] { height: 3.5rem !important; }
    [data-testid="stLogo"] img {
        height: 3.5rem !important; max-height: 3.5rem !important; width: auto !important;
    }

    /* Cards: fundo vem do tema; se a variável não existir, usa um tom
       translúcido derivado da cor do texto (funciona em claro e escuro) */
    div[class*="st-key-card_"] {
        /* fallback para navegadores sem suporte a cor relativa */
        background: color-mix(in srgb, currentColor 7%, transparent);
        /* branco opaco com texto escuro (claro); translúcido com texto claro (escuro) */
        background: rgb(from currentColor 255 255 255 / calc(1 - r / 255));
        border: 1px solid rgba(128, 128, 128, .25);
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
        padding: 1.1rem 1.25rem;
    }

    /* JSON com um leve tom próprio, para não sumir dentro do card branco */
    div[class*="st-key-card_json"] [data-testid="stCode"],
    div[class*="st-key-card_json"] pre {
        background: color-mix(in srgb, currentColor 3%, transparent) !important;
    }
    .card-title {
        font-size: 0.95rem; font-weight: 700; letter-spacing: .02em;
        color: inherit; margin: 0;
    }
    .linha { margin: 0.35rem 0; color: inherit; font-size: 0.95rem; }
    .linha b { color: inherit; }

    /* Pílulas: fundos translúcidos funcionam nos dois temas */
    .pill {
        display: inline-block; padding: 2px 12px; border-radius: 999px;
        font-size: 0.78rem; font-weight: 600; margin-right: 6px; white-space: nowrap;
    }
    .pill.red    { background: rgba(239, 68, 68, .16);  color: #EF4444; }
    .pill.blue   { background: rgba(59, 130, 246, .16); color: #3B82F6; }
    .pill.orange { background: rgba(249, 115, 22, .16); color: #F97316; }
    .pill.gray   { background: rgba(128, 128, 128, .14); color: inherit;
                   border: 1px solid rgba(128, 128, 128, .3); }
    .topo { display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 0.6rem; }

    /* Papel do laudo: sempre claro, com texto escuro fixo (simula o documento) */
    .papel {
        background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, .12);
        padding: 28px 32px 32px; color: #1E293B; font-family: Arial, sans-serif;
    }
    .papel h4 { text-align: center; margin: 0 0 4px; color: #0F172A; }
    .papel .sub { text-align: center; font-weight: 700; margin: 0 0 22px; color: #1E293B; }
    .papel p { margin: 6px 0; color: #1E293B; }
    .papel b { color: #0F172A; }
    .papel .exame-img { text-align: center; margin-top: 28px; }
    .papel .exame-img img { width: 70%; border-radius: 4px; }
</style>
""",
    unsafe_allow_html=True,
)


def pill(texto: str, cor: str = "gray") -> str:
    return f'<span class="pill {cor}">{texto}</span>'


def linha(rotulo: str, valor: str) -> str:
    return f'<p class="linha"><b>{rotulo}:</b> {valor}</p>'


def imagem_base64(caminho: Path) -> str:
    """Retorna o HTML da imagem embutida, ou string vazia se não existir."""
    if not Path(caminho).exists():
        return ""
    b64 = base64.b64encode(Path(caminho).read_bytes()).decode()
    return (
        '<div class="exame-img">'
        f'<img src="data:image/png;base64,{b64}" alt="Imagem do exame">'
        "</div>"
    )


# ------------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------------
if CAMINHO_LOGO.exists():
    st.logo(str(CAMINHO_LOGO), size="large")

with st.sidebar:
    st.markdown("<div style='height: 35vh;'></div>", unsafe_allow_html=True)
    st.divider()
    st.caption("⚙️ Configurações")
    st.caption("🚪 Sair")

# ------------------------------------------------------------------
# CABEÇALHO
# ------------------------------------------------------------------
st.title("Dashboard")

col_esq, col_dir = st.columns(2, gap="large")

# ------------------------------------------------------------------
# ESQUERDA: VISUALIZAÇÃO DO DOCUMENTO
# ------------------------------------------------------------------
with col_esq, st.container(key="card_preview"):
    d = DADOS["documento"]

    st.markdown(
        f'<div class="topo"><p class="card-title">VISUALIZAÇÃO DO DOCUMENTO</p>'
        f"{pill('📄 ' + DADOS['status_upload'])}</div>",
        unsafe_allow_html=True,
    )

    # Área com scroll interno, como no protótipo
    with st.container(height=ALTURA_PREVIEW, border=True):
        # IMPORTANTE: sem indentação no HTML, senão vira bloco de código
        html_laudo = (
            '<div class="papel">'
            f"<h4>{d['hospital']}</h4>"
            f'<p class="sub">{d["titulo"]}</p>'
            f"<p><b>Paciente:</b> {d['paciente']}</p>"
            f"<p><b>Solicitante:</b> {d['solicitante']}</p>"
            f"<p><b>Exame:</b> {d['exame']}</p>"
            '<p style="margin-top:16px;"><b>CONCLUSÃO:</b></p>'
            f"<p>{d['conclusao']}</p>"
            f"{imagem_base64(d['imagem'])}"
            "</div>"
        )
        st.markdown(html_laudo, unsafe_allow_html=True)

        if not Path(d["imagem"]).exists():
            st.info("Adicione a imagem do exame em assets/exame_torax.png")

# ------------------------------------------------------------------
# DIREITA: PACIENTE / DADOS CLÍNICOS / JSON
# ------------------------------------------------------------------
with col_dir:
    # INFORMAÇÃO DO PACIENTE
    with st.container(key="card_paciente"):
        p = DADOS["paciente"]
        st.markdown(
            '<p class="card-title">INFORMAÇÃO DO PACIENTE</p>'
            + linha("Nome", p["nome"])
            + linha("Idade", str(p["idade"])),
            unsafe_allow_html=True,
        )

    st.write("")

    # DADOS CLÍNICOS
    with st.container(key="card_clinico"):
        c = DADOS["clinico"]
        badges = "".join(pill(t, cor) for t, cor in c["badges"])
        st.markdown(
            f'<div class="topo"><p class="card-title">DADOS CLÍNICOS</p>'
            f"{pill(c['urgencia'], 'red')}</div>"
            + linha("Médico Solicitante", c["medico"])
            + linha("CRM", c["crm"])
            + linha("Exame Realizado", c["exame"])
            + linha("Diagnóstico Principal", c["diagnostico"])
            + linha("CID Sugerido", c["cid"])
            + f'<p class="linha"><b>Risk badges:</b> {badges}</p>',
            unsafe_allow_html=True,
        )

    st.write("")

    # VISUALIZAÇÃO DO JSON
    with st.container(key="card_json"):
        st.markdown(
            '<p class="card-title">VISUALIZAÇÃO DO JSON</p>', unsafe_allow_html=True
        )
        st.code(
            json.dumps(DADOS["payload"], indent=2, ensure_ascii=False),
            language="json",
            height=ALTURA_JSON,
        )
