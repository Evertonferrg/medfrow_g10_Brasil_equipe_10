"""H5.2.1 T2 — histórico de triagens com filtros (GET /historico)."""

import os
import sys
from datetime import timedelta
from pathlib import Path

import requests
import streamlit as st

RAIZ_UI = Path(__file__).resolve().parents[1]
if str(RAIZ_UI) not in sys.path:
    sys.path.insert(0, str(RAIZ_UI))

from componentes.fila import ROTULO_STATUS
from componentes.historico import (
    DESTINOS,
    FUSO,
    MENSAGEM_VAZIO,
    PRIORIDADES,
    STATUS,
    TIPOS,
    hoje,
    montar_params,
)
from services.estilo import preparar_pagina

API_URL = os.getenv("API_URL", "http://localhost:8000")
DIAS_PADRAO = 30  # período inicial do filtro

st.set_page_config(page_title="Histórico", page_icon="🩺", layout="wide")
preparar_pagina()

st.title("Histórico de Triagens")


# ------------------------------------------------------------------
# HELPERS (Motivo de rejeição com cache)
# ------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def buscar_motivo_rejeicao(doc_id: str) -> str:
    """Busca o motivo no detalhe caso o documento esteja rejeitado."""
    try:
        r = requests.get(f"{API_URL}/documentos/{doc_id}", timeout=5)
        if r.status_code == 200:
            dados = r.json()
            if dados.get("motivo_rejeicao"):
                return str(dados["motivo_rejeicao"]).strip()
            just = (dados.get("decisao_roteamento") or {}).get(
                "justificativa_roteamento"
            ) or ""
            if "Motivo:" in just:
                return just.split("Motivo:")[-1].strip()
    except (requests.RequestException, ValueError, KeyError):
        pass
    return ""


def formatar_status_com_motivo(doc_id: str, status_bruto: str | None) -> str:
    rotulo = ROTULO_STATUS.get(status_bruto, status_bruto or "—")
    if str(status_bruto).lower() == "rejeitado":
        motivo = buscar_motivo_rejeicao(doc_id)
        if motivo:
            return f"Rejeitado — {motivo}"
    return rotulo


def resetar_filtros() -> None:
    """Incrementa a versão das chaves para limpar o formulário."""
    st.session_state["filtro_versao"] = st.session_state.get("filtro_versao", 0) + 1
    st.rerun()


# Controle de versão das chaves dos inputs
v = st.session_state.get("filtro_versao", 0)

# ------------------------------------------------------------------
# FILTROS
# ------------------------------------------------------------------
with st.container(key="card_filtros"), st.form("filtros_historico", border=False):
    periodo = st.date_input(
        "Período de chegada",
        value=(hoje() - timedelta(days=DIAS_PADRAO), hoje()),
        format="DD/MM/YYYY",
        key=f"hist_periodo_{v}",
    )
    c1, c2 = st.columns(2)
    tipos = c1.multiselect("Tipo de documento", TIPOS, key=f"hist_tipos_{v}")
    prioridades = c2.multiselect("Prioridade", PRIORIDADES, key=f"hist_prioridades_{v}")
    destinos = c1.multiselect("Destino", DESTINOS, key=f"hist_destinos_{v}")
    status = c2.multiselect(
        "Status",
        STATUS,
        format_func=lambda s: ROTULO_STATUS.get(s, s),
        key=f"hist_status_{v}",
    )
    st.form_submit_button("Filtrar", type="primary", icon=":material/search:")

if not isinstance(periodo, (list, tuple)) or len(periodo) != 2:
    st.info("Escolha a data final do período.")
    st.stop()

# ------------------------------------------------------------------
# CONSULTA (GET /historico)
# ------------------------------------------------------------------
try:
    resposta = requests.get(
        f"{API_URL}/historico",
        params=montar_params(*periodo, tipos, prioridades, destinos, status),
        timeout=10,
    )
    if resposta.status_code == 422:
        try:
            detalhe = resposta.json().get("detail")
        except ValueError:
            detalhe = None
        st.warning(detalhe if isinstance(detalhe, str) else "Filtro inválido.")
        st.stop()
    resposta.raise_for_status()
    itens = resposta.json()
except (requests.RequestException, ValueError):
    st.error("Não foi possível carregar o histórico. Tente novamente em instantes.")
    st.stop()

if not isinstance(itens, list):
    st.error("Não foi possível carregar o histórico. Tente novamente em instantes.")
    st.stop()

st.write("")

# ------------------------------------------------------------------
# ESTADO VAZIO COM BOTÃO "LIMPAR FILTROS"
# ------------------------------------------------------------------
if not itens:
    st.info(MENSAGEM_VAZIO)
    col_limpar, _ = st.columns([1, 4])
    with col_limpar:
        if st.button(
            "Limpar filtros",
            icon=":material/filter_alt_off:",
            type="secondary",
            use_container_width=True,
        ):
            resetar_filtros()
    st.stop()

# ------------------------------------------------------------------
# MONTAGEM DAS LINHAS (Com data de Brasília e motivo de rejeição)
# ------------------------------------------------------------------
linhas = []
for i in itens:
    try:
        from datetime import datetime

        chegada = datetime.fromisoformat(i["chegada_em"]).astimezone(FUSO)
        data_formatada = chegada.strftime("%d/%m/%Y %H:%M")
    except (ValueError, KeyError):
        data_formatada = str(i.get("chegada_em", "—"))

    linhas.append(
        {
            "Documento": i.get("documento_id", "—"),
            "Chegada": data_formatada,
            "Tipo": i.get("tipo") or "—",
            "Prioridade": i.get("prioridade") or "—",
            "Destino": str(i.get("destino") or "—").replace("_", " "),
            "Status": formatar_status_com_motivo(
                i.get("documento_id"), i.get("status")
            ),
        }
    )

# ------------------------------------------------------------------
# RESULTADOS
# ------------------------------------------------------------------
with st.container(key="card_historico_lista"):
    st.markdown(
        '<p class="card-title" style="font-weight:700;margin:0">RESULTADOS</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"{len(linhas)} documento(s) encontrado(s), do mais recente ao mais antigo."
    )
    st.dataframe(linhas, hide_index=True, width="stretch")
