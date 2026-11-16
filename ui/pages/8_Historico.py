"""H5.2.1 T2 — histórico de triagens com filtros (GET /historico)."""

import os
from pathlib import Path

import requests
import streamlit as st

from ui.componentes.fila import ROTULO_STATUS
from ui.componentes.historico import (
    DESTINOS,
    MENSAGEM_VAZIO,
    PRIORIDADES,
    STATUS,
    TIPOS,
    hoje,
    linhas_tabela,
    montar_params,
)

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Histórico", layout="wide")

CAMINHO_LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo.png"
if CAMINHO_LOGO.exists():
    st.logo(str(CAMINHO_LOGO), size="large")

st.title("Histórico de triagens")

with st.form("filtros_historico"):
    periodo = st.date_input(
        "Período de chegada",
        value=(hoje(), hoje()),
        format="DD/MM/YYYY",
    )
    c1, c2 = st.columns(2)
    tipos = c1.multiselect("Tipo de documento", TIPOS)
    prioridades = c2.multiselect("Prioridade", PRIORIDADES)
    destinos = c1.multiselect("Destino", DESTINOS)
    status = c2.multiselect(
        "Status", STATUS, format_func=lambda s: ROTULO_STATUS.get(s, s)
    )
    st.form_submit_button("Filtrar")

if len(periodo) != 2:  # o usuário escolheu só a data inicial por enquanto
    st.info("Escolha a data final do período.")
    st.stop()

try:
    resposta = requests.get(
        f"{API_URL}/historico",
        params=montar_params(*periodo, tipos, prioridades, destinos, status),
        timeout=10,
    )
    if resposta.status_code == 422:
        st.warning(resposta.json().get("detail", "Filtro inválido."))
        st.stop()
    resposta.raise_for_status()
    itens = resposta.json()
except requests.RequestException:
    st.error("Não foi possível carregar o histórico. Tente novamente em instantes.")
    st.stop()

if not itens:
    st.info(MENSAGEM_VAZIO)
else:
    st.caption(
        f"{len(itens)} documento(s) encontrado(s), do mais recente ao mais antigo."
    )
    st.dataframe(linhas_tabela(itens), hide_index=True, width="stretch")
