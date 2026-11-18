import sys
from pathlib import Path

import streamlit as st

RAIZ_UI = Path(__file__).resolve().parents[1]
if str(RAIZ_UI) not in sys.path:
    sys.path.insert(0, str(RAIZ_UI))

from services.detalhe import (
    buscar_resultado,
    canal_de_origem,
    mostrar_detalhe,
    mostrar_original_do_caso,
    selo_status,
)
from services.estilo import PAGINA_LISTA, preparar_pagina
from services.navegacao import abrir_revisao, caso_atual, definir_caso

ALTURA_PREVIEW = 720

st.set_page_config(page_title="Dashboard · MediFlow", page_icon="🩺", layout="wide")
preparar_pagina()

st.title("Dashboard")
doc_id = caso_atual()

# ------------------------------------------------------------------
# TOPO: comportamento diferente para tela vazia vs. caso aberto
# ------------------------------------------------------------------
if not doc_id:
    # Tela vazia: exibe busca manual para o usuário digitar um ID diretamente
    st.info("Digite o ID de um documento ou abra um caso pela lista de documentos.")
    with st.form("buscar_caso", border=False):
        f1, f2 = st.columns([4, 1], vertical_alignment="bottom")
        texto = f1.text_input(
            "ID do documento",
            placeholder="DOC-CLIN-2026-8942",
            label_visibility="collapsed",
        )
        buscar = f2.form_submit_button(
            "Abrir caso",
            type="primary",
            icon=":material/open_in_new:",
            use_container_width=True,
        )
    if buscar and texto.strip():
        definir_caso(texto.strip())
        st.query_params["id"] = texto.strip()
        st.rerun()
    st.stop()

# Caso já carregado: só o link discreto de voltar à lista
with st.container(key="btn_voltar"):
    st.page_link(PAGINA_LISTA, label="Voltar para a lista", icon=":material/arrow_back:")

if st.query_params.get("id") != doc_id:
    st.query_params["id"] = doc_id  # garante que a URL sempre reflete o caso aberto

# ------------------------------------------------------------------
# CONSULTA (GET /documentos/{id})
# ------------------------------------------------------------------
@st.fragment(run_every=3)
def aguardar(doc_id: str) -> None:
    """Enquanto a API processa, consulta de 3 em 3 segundos e atualiza sozinho."""
    estado, _ = buscar_resultado(doc_id)
    if estado == "processando":
        st.info(f"Analisando o documento **{doc_id}**... a página atualiza sozinha.")
    else:
        st.rerun()


estado, res = buscar_resultado(doc_id)

if estado == "processando":
    aguardar(doc_id)
    st.stop()

mensagens = {
    "nao_encontrado": ("warning", "Documento não encontrado. Confira o ID."),
    "invalido": ("error", "ID de documento inválido."),
    "erro": ("error", "Não foi possível consultar a API. Verifique se ela está no ar."),
}
if estado != "ok":
    tipo, texto_msg = mensagens[estado]
    getattr(st, tipo)(texto_msg)
    st.stop()

# ------------------------------------------------------------------
# CASO
# ------------------------------------------------------------------
origem = canal_de_origem(doc_id)
st.caption(f"Documento {doc_id}" + (f" · Origem: {origem}" if origem else ""))

dec = res.get("decisao_roteamento") or {}
if dec.get("requer_auditoria_humana"):
    with st.container(key="card_revisao"):
        a, b = st.columns([4, 1], vertical_alignment="center")
        a.markdown("**Este caso precisa de revisão humana.** Confira os pontos de atenção e decida.")
        if b.button("Revisar caso", type="primary", icon=":material/open_in_new:", use_container_width=True, key="btn_revisar"):
            abrir_revisao(doc_id)

col_esq, col_dir = st.columns([5, 6], gap="large")

with col_esq, st.container(key="card_preview"):
    st.markdown(
        f'<div class="topo"><p class="card-title">DOCUMENTO ORIGINAL</p>{selo_status(res)}</div>',
        unsafe_allow_html=True,
    )
    with st.container(height=ALTURA_PREVIEW, border=True):
        mostrar_original_do_caso(doc_id)

with col_dir:
    mostrar_detalhe(res)