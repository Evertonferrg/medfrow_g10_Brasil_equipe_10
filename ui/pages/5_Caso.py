"""H3.4.1 T2/T3 — resumo do caso em uma tela (sem rolagem em 1366x768)."""

import os
import sys
from pathlib import Path

# Garante que `from ui...` funcione mesmo abrindo a página direto pela URL.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
import streamlit as st

from ui.componentes.caso import dados_do_caso
from ui.componentes.original import mostrar_original

API_URL = os.getenv("API_URL", "http://localhost:8000")

# Compacta as margens para caber em notebook. NÃO chame st.set_page_config
# aqui: o ui/app.py já chama e repetir causa erro.
st.markdown(
    "<style>.block-container{padding-top:2.5rem;padding-bottom:0.5rem}</style>",
    unsafe_allow_html=True,
)

documento_id = st.query_params.get("id") or st.session_state.get("caso_id")
if not documento_id:
    st.info("Nenhum caso selecionado. Abra um caso pela fila de emergência.")
    st.stop()


@st.dialog("Documento original", width="large")
def _dialogo_original(doc_id: str) -> None:
    try:
        resp = httpx.get(f"{API_URL}/documentos/{doc_id}/original", timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError:
        st.error("Não foi possível carregar o documento original.")
        return
    mostrar_original(st, resp.content, resp.headers.get("content-type", ""))


try:
    # GET /documentos/{id}: resultado da triagem em JSON (202 se ainda processa).
    resp = httpx.get(f"{API_URL}/documentos/{documento_id}", timeout=10)
    resp.raise_for_status()
except httpx.HTTPError:
    st.error("Não foi possível carregar o caso.")
    st.stop()

if resp.status_code == 202:
    st.info(
        "Este documento ainda está sendo processado. Recarregue em alguns segundos."
    )
    st.stop()

caso = dados_do_caso(resp.json())

# A origem não vem no resultado: busca na listagem (a mesma de "Meus envios").
if caso["origem"] == "—":
    try:
        lista = httpx.get(f"{API_URL}/documentos", timeout=10).json()
        canal = next(
            (
                d.get("canal_origem")
                for d in lista
                if d.get("documento_id") == documento_id
            ),
            None,
        )
        if canal:
            caso["origem"] = canal
    except (httpx.HTTPError, ValueError):
        pass  # sem origem, fica "—"

st.subheader("Resumo do caso")
esquerda, direita = st.columns(2)
with esquerda:
    st.caption("Paciente")
    st.markdown(f"**{caso['paciente']}**")
    st.caption("Origem")
    st.markdown(caso["origem"])
with direita:
    st.caption("Achado principal")
    st.markdown(f"**{caso['achado']}**")
    st.caption("CID")
    st.markdown(caso["cid"])
    st.caption("Médico solicitante")
    st.markdown(caso["medico"])

if st.button("Ver original", type="primary"):
    _dialogo_original(documento_id)
