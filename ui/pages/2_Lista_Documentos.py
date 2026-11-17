import math
import os
import sys
from pathlib import Path
from services.navegacao import abrir_caso

import requests
import streamlit as st

# Garante importação dos módulos locais mesmo executando de diretórios diferentes
RAIZ_UI = Path(__file__).resolve().parents[1]
if str(RAIZ_UI) not in sys.path:
    sys.path.insert(0, str(RAIZ_UI))

from services.detalhe import mostrar_detalhe
from services.estilo import PAGINA_DASHBOARD, PAGINA_NOVO, pill, preparar_pagina

# ------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ------------------------------------------------------------------
st.set_page_config(page_title="Documentos · MediFlow", page_icon="🩺", layout="wide")
preparar_pagina()

API = os.getenv("API_URL", "http://localhost:8000")
CANAIS = ["Todos", "Pronto_Socorro", "Ambulatorio", "Laboratorio", "Operadora"]
POR_PAGINA = 5

COR_PRIORIDADE = {
    "urgente": "red",
    "emergência": "red",
    "emergencia": "red",
    "alta": "orange",
    "rotina": "green",
    "baixa": "green",
}

# Larguras das 6 colunas da tabela
LARGURAS = [2.6, 2.2, 2.2, 1.4, 1.4, 1.4]


def cor_status(status: str) -> str:
    s = status.lower()
    if "erro" in s or "rejeit" in s:
        return "red"
    if "revis" in s or "pend" in s:
        return "yellow"
    if s == "processado":
        return "green"
    if "receb" in s or "process" in s or "fila" in s:
        return "blue"
    return "gray"


def rotulo_status(status: str) -> str:
    return status.replace("_", " ").capitalize()


def voltar_pagina_1() -> None:
    st.session_state["pagina"] = 1


def buscar_lista(canal: str) -> list | None:
    """GET /documentos. Devolve None se a API não respondeu."""
    params = {} if canal == "Todos" else {"canal_origem": canal}
    try:
        r = requests.get(f"{API}/documentos", params=params, timeout=30)
        r.raise_for_status()
        dados = r.json()
    except (requests.RequestException, ValueError):
        return None
    return dados if isinstance(dados, list) else None


def buscar_detalhe(doc_id: str) -> tuple[str, dict | None]:
    """GET /documentos/{id}. Estados: ok, processando, nao_encontrado, erro."""
    try:
        det = requests.get(f"{API}/documentos/{doc_id}", timeout=30)
    except requests.RequestException:
        return "erro", None
    if det.status_code == 200:
        try:
            return "ok", det.json()
        except ValueError:
            return "erro", None
    if det.status_code == 202:
        return "processando", None
    if det.status_code == 404:
        return "nao_encontrado", None
    return "erro", None


# ------------------------------------------------------------------
# CABEÇALHO (Título + Botão "+ Novo Documento")
# ------------------------------------------------------------------
col_tit, col_btn = st.columns([4, 1], vertical_alignment="bottom")
with col_tit:
    st.title("Documentos Clínicos")
    st.caption("Gerencie o repositório de laudos, receitas e guias enviados.")
with col_btn, st.container(key="btn_novo"):
    st.page_link(
        PAGINA_NOVO,
        label="Novo Documento",
        icon=":material/add:",
        use_container_width=True,
    )

# ------------------------------------------------------------------
# FILTROS (pesquisa por texto + canal de origem)
# ------------------------------------------------------------------
col_busca, col_canal = st.columns([3, 1], vertical_alignment="bottom")

with col_busca:
    busca = st.text_input(
        "Pesquisar",
        key="busca_docs",
        placeholder="Pesquisar por ID, tipo de documento ou destino",
        icon=":material/search:",
        label_visibility="collapsed",
        on_change=voltar_pagina_1,
    )

with col_canal:
    canal = st.selectbox(
        "Canal de origem",
        CANAIS,
        label_visibility="collapsed",
        on_change=voltar_pagina_1,
        help="Filtrar por canal de origem",
    )

# ------------------------------------------------------------------
# CONSULTA AO BACKEND (GET /documentos)
# ------------------------------------------------------------------
itens_api = buscar_lista(canal)
if itens_api is None:
    st.error("Não consegui conectar com a API. Verifique se ela está no ar.")
    st.stop()
if not itens_api:
    st.info("Nenhum documento encontrado para este canal de origem.")
    st.stop()

DOCUMENTOS = [
    {
        "id": str(item.get("documento_id", "—")),
        "tipo": item.get("tipo_documento") or "Não classificado",
        "destino": item.get("destino") or item.get("canal_origem") or "—",
        "prioridade": item.get("nivel_prioridade") or "Rotina",
        "status": str(item.get("status") or "processado"),
        "canal_origem": item.get("canal_origem", ""),
    }
    for item in itens_api
]

termo = busca.strip().lower()
filtrados = [
    d
    for d in DOCUMENTOS
    if not termo
    or termo in f"{d['id']} {d['tipo']} {d['destino']} {d['status']} {d['canal_origem']}".lower()
]

# ------------------------------------------------------------------
# LISTA COM PAGINAÇÃO
# ------------------------------------------------------------------
total_paginas = max(1, math.ceil(len(filtrados) / POR_PAGINA))
pagina = min(st.session_state.get("pagina", 1), total_paginas)

inicio = (pagina - 1) * POR_PAGINA
itens = filtrados[inicio : inicio + POR_PAGINA]

doc_selecionado = st.session_state.get("doc_selecionado")

with st.container(key="card_lista"):
    if not itens:
        st.info("Nenhum documento encontrado com o termo pesquisado.")
    else:
        cab = st.columns(LARGURAS)
        titulos = ["ID", "Tipo de Documento", "Destino / Origem", "Prioridade", "Status", "Ação"]
        for col, texto in zip(cab, titulos):
            col.markdown(f"<b style='font-size:.85rem'>{texto}</b>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:.25rem 0 .5rem;opacity:.3'>", unsafe_allow_html=True)

        for d in itens:
            c1, c2, c3, c4, c5, c6 = st.columns(LARGURAS, vertical_alignment="center")

            marcador = "🔵 " if d["id"] == doc_selecionado else ""
            c1.markdown(f"<span style='font-size:.9rem;font-weight:600'>{marcador}{d['id']}</span>", unsafe_allow_html=True)
            c2.markdown(f"<span style='font-size:.9rem'>{d['tipo']}</span>", unsafe_allow_html=True)
            c3.markdown(f"<span style='font-size:.9rem'>{d['destino']}</span>", unsafe_allow_html=True)
            c4.markdown(pill(d["prioridade"], COR_PRIORIDADE.get(d["prioridade"].lower(), "gray")), unsafe_allow_html=True)
            c5.markdown(pill(rotulo_status(d["status"]), cor_status(d["status"])), unsafe_allow_html=True)

            lbl_btn = "Detalhes" if d["id"] != doc_selecionado else "Ocultar"
            if c6.button(lbl_btn, key=f"sel_{d['id']}", icon=":material/visibility:", use_container_width=True):
                st.session_state["doc_selecionado"] = None if d["id"] == doc_selecionado else d["id"]
                st.rerun()

            st.markdown("<hr style='margin:.4rem 0;opacity:.15'>", unsafe_allow_html=True)

        # Paginação
        _, p1, p2, p3, _ = st.columns([3, 1, 2, 1, 3], vertical_alignment="center")
        with p1:
            if st.button("", icon=":material/chevron_left:", disabled=pagina <= 1, key="pg_ant", use_container_width=True):
                st.session_state["pagina"] = pagina - 1
                st.rerun()
        with p2:
            st.markdown(f"<div style='text-align:center'>Página {pagina} de {total_paginas}</div>", unsafe_allow_html=True)
        with p3:
            if st.button("", icon=":material/chevron_right:", disabled=pagina >= total_paginas, key="pg_prox", use_container_width=True):
                st.session_state["pagina"] = pagina + 1
                st.rerun()

# ------------------------------------------------------------------
# DETALHE DO DOCUMENTO SELECIONADO + "ABRIR CASO"
# ------------------------------------------------------------------
if doc_selecionado:
    st.divider()
    col_detalhe_tit, col_detalhe_btn = st.columns([4, 1], vertical_alignment="center")
    with col_detalhe_tit:
        st.subheader(f"Detalhe: {doc_selecionado}")
    with col_detalhe_btn:
        if st.button("Abrir caso", key=f"abrir_{doc_selecionado}", type="primary", icon=":material/open_in_new:", use_container_width=True):
            abrir_caso(doc_selecionado)

    with st.spinner("Carregando detalhes do documento..."):
        estado, res = buscar_detalhe(doc_selecionado)

    if estado == "ok":
        mostrar_detalhe(res)
    elif estado == "processando":
        st.info("Este documento ainda está sendo processado. Atualize a página em instantes.")
    elif estado == "nao_encontrado":
        st.warning("Documento não encontrado.")
    else:
        st.error("Não foi possível carregar os detalhes. Verifique se a API está no ar.")