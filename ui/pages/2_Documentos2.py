import math

import streamlit as st
from services.estilo import PAGINA_DASHBOARD, PAGINA_NOVO, pill, preparar_pagina

st.set_page_config(page_title="Documentos · MediFlow", page_icon="🩺", layout="wide")
preparar_pagina()

# ------------------------------------------------------------------
# MOCK: depois vem do endpoint de lista do backend (com paginação)
# ------------------------------------------------------------------
DOCUMENTOS = [
    {
        "id": "DOC-CLIN-2026-8942",
        "tipo": "Laudo de Imagem",
        "paciente": "Carlos Eduardo Mendes",
        "prioridade": "Urgente",
        "status": "Processado",
    },
    {
        "id": "DOC-CLIN-2026-8941",
        "tipo": "Receita",
        "paciente": "Renata Silveira",
        "prioridade": "Rotina",
        "status": "Processado",
    },
    {
        "id": "DOC-CLIN-2026-8940",
        "tipo": "Laudo de Imagem",
        "paciente": "Carlos Eduardo Mendes",
        "prioridade": "Urgente",
        "status": "Em fila",
    },
    {
        "id": "DOC-CLIN-2026-8943",
        "tipo": "Guia",
        "paciente": "Carlos Eduardo Mendes",
        "prioridade": "Urgente",
        "status": "Processado",
    },
    {
        "id": "DOC-CLIN-2026-8944",
        "tipo": "Alta",
        "paciente": "Renata Silveira",
        "prioridade": "Rotina",
        "status": "Erro",
    },
    {
        "id": "DOC-CLIN-2026-8945",
        "tipo": "Atestado",
        "paciente": "Carlos Eduardo Mendes",
        "prioridade": "Rotina",
        "status": "Processado",
    },
    {
        "id": "DOC-CLIN-2026-8946",
        "tipo": "Receita",
        "paciente": "Renata Silveira",
        "prioridade": "Rotina",
        "status": "Processado",
    },
]
POR_PAGINA = 5

COR_PRIORIDADE = {"Urgente": "red", "Alta": "orange", "Rotina": "green"}
COR_STATUS = {"Processado": "green", "Em fila": "blue", "Erro": "red"}

LARGURAS = [3, 2.5, 3, 1.5, 1.5, 0.8]


def voltar_pagina_1() -> None:
    st.session_state["pagina"] = 1


# ------------------------------------------------------------------
# CABEÇALHO
# ------------------------------------------------------------------
col_tit, col_btn = st.columns([4, 1], vertical_alignment="bottom")
with col_tit:
    st.title("Documentos Clínicos")
    st.caption("Gerencie o repositório de laudos, receitas e guias.")
with col_btn, st.container(key="btn_novo"):
    st.page_link(
        PAGINA_NOVO,
        label="Novo Documento",
        icon=":material/add:",
        use_container_width=True,
    )

# ------------------------------------------------------------------
# PESQUISA
# ------------------------------------------------------------------
busca = st.text_input(
    "Pesquisar",
    key="busca_docs",
    placeholder="Pesquisar por ID, paciente ou tipo de documento",
    icon=":material/search:",
    label_visibility="collapsed",
    on_change=voltar_pagina_1,
)
termo = busca.strip().lower()
filtrados = [
    d
    for d in DOCUMENTOS
    if not termo or termo in f"{d['id']} {d['tipo']} {d['paciente']}".lower()
]

# ------------------------------------------------------------------
# LISTA (cada linha abre o Dashboard)
# ------------------------------------------------------------------
total_paginas = max(1, math.ceil(len(filtrados) / POR_PAGINA))
pagina = min(st.session_state.get("pagina", 1), total_paginas)

inicio = (pagina - 1) * POR_PAGINA
itens = filtrados[inicio : inicio + POR_PAGINA]

with st.container(key="card_lista"):
    if not itens:
        st.info("Nenhum documento encontrado nesta lista.")
        if busca.strip() and st.button(
            f"Abrir ID “{busca.strip()}” no Dashboard", type="primary"
        ):
            st.session_state["ultimo_documento_id"] = busca.strip()
            st.switch_page(PAGINA_DASHBOARD)
    else:
        cab = st.columns(LARGURAS)
        for col, texto in zip(
            cab, ["ID", "Tipo de Documento", "Paciente", "Prioridade", "Status", ""]
        ):
            col.markdown(
                f"<b style='font-size:.85rem'>{texto}</b>", unsafe_allow_html=True
            )
        st.markdown(
            "<hr style='margin:.25rem 0 .5rem;opacity:.3'>", unsafe_allow_html=True
        )

        for d in itens:
            c1, c2, c3, c4, c5, c6 = st.columns(LARGURAS, vertical_alignment="center")
            c1.markdown(
                f"<span style='font-size:.9rem'>{d['id']}</span>",
                unsafe_allow_html=True,
            )
            c2.markdown(
                f"<span style='font-size:.9rem'>{d['tipo']}</span>",
                unsafe_allow_html=True,
            )
            c3.markdown(
                f"<span style='font-size:.9rem'>{d['paciente']}</span>",
                unsafe_allow_html=True,
            )
            c4.markdown(
                pill(d["prioridade"], COR_PRIORIDADE.get(d["prioridade"], "gray")),
                unsafe_allow_html=True,
            )
            c5.markdown(
                pill(d["status"], COR_STATUS.get(d["status"], "gray")),
                unsafe_allow_html=True,
            )
            if c6.button(
                "",
                key=f"abrir_{d['id']}",
                icon=":material/arrow_forward:",
                help="Abrir no Dashboard",
            ):
                st.session_state["ultimo_documento_id"] = d["id"]
                st.switch_page(PAGINA_DASHBOARD)
            st.markdown(
                "<hr style='margin:.4rem 0;opacity:.15'>", unsafe_allow_html=True
            )

        # Paginação
        _, p1, p2, p3, _ = st.columns([3, 1, 2, 1, 3], vertical_alignment="center")
        with p1:
            if st.button(
                "",
                icon=":material/chevron_left:",
                disabled=pagina <= 1,
                key="pg_ant",
                use_container_width=True,
            ):
                st.session_state["pagina"] = pagina - 1
                st.rerun()
        with p2:
            st.markdown(
                f"<div style='text-align:center'>Página {pagina} de {total_paginas}</div>",
                unsafe_allow_html=True,
            )
        with p3:
            if st.button(
                "",
                icon=":material/chevron_right:",
                disabled=pagina >= total_paginas,
                key="pg_prox",
                use_container_width=True,
            ):
                st.session_state["pagina"] = pagina + 1
                st.rerun()
