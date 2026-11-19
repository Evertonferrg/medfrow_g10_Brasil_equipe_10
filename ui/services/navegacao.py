"""Porta única para abrir um caso (Dashboard)."""

import streamlit as st

from services.estilo import PAGINA_DASHBOARD
from datetime import datetime, timedelta, timezone

def definir_caso(documento_id: str) -> None:
    """Guarda o caso atual na sessão (as chaves antigas continuam valendo)."""
    st.session_state["caso_id"] = documento_id
    st.session_state["ultimo_documento_id"] = documento_id


def abrir_caso(documento_id: str) -> None:
    """Guarda o caso, põe o ID na URL e vai para o Dashboard."""
    definir_caso(documento_id)
    st.query_params["id"] = documento_id
    st.switch_page(PAGINA_DASHBOARD)


def caso_atual() -> str | None:
    """ID do caso: sessão primeiro, depois a URL (?id=), depois o último enviado."""
    ss = st.session_state
    valor = ss.get("caso_id") or st.query_params.get("id") or ss.get("ultimo_documento_id")
    valor = str(valor).strip() if valor else ""
    return valor or None

PAGINA_REVISAO = "pages/13_UI_Revisao_de_Caso.py"

def abrir_revisao(documento_id: str) -> None:
    """Abre o painel de revisão da equipe, que só lê o ID da URL (?id=...).

    O Streamlit limpa a URL ao trocar de página; por isso o ID fica marcado na
    sessão e é devolvido à URL por preparar_pagina() na página de destino.
    """
    definir_caso(documento_id)
    st.session_state["_id_para_url"] = documento_id
    st.switch_page(PAGINA_REVISAO)