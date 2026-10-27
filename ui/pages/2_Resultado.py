"""T4 — tela de resultado: consulta GET /documentos/{documento_id} e mostra
o tipo identificado, o score de confiança ao lado do tipo e a especialidade provável ao analista."""
import os
import sys
from pathlib import Path

import requests
import streamlit as st

PASTA_UI = str(Path(__file__).resolve().parents[1])
if PASTA_UI not in sys.path:
    sys.path.insert(0, PASTA_UI)

from componentes.classificacao import (  # noqa: E402, F401
    carregar_limite_confianca,
    exibir_classificacao,
    formatar_confianca,
)
from componentes.diagnostico import bloco_diagnostico  # noqa: E402, F401
from componentes.medico import bloco_medico  # noqa: E402, F401

API = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="MediFlow — Resultado", page_icon="🔎", layout="wide")
st.title("🔎 Resultado da triagem")

with st.form("consulta"):
    doc_id = st.text_input("ID do documento", placeholder="DOC-CLIN-2026-8942")
    buscar = st.form_submit_button("Buscar resultado")

if buscar and doc_id.strip():
    try:
        r = requests.get(f"{API}/documentos/{doc_id.strip()}", timeout=30)
    except requests.RequestException as exc:
        st.error(f"Não consegui falar com a API: {exc}")
        st.stop()

    if r.status_code == 400:
        st.error(r.json().get("detail", "documento_id inválido"))
    elif r.status_code == 404:
        st.warning("Documento não encontrado. Confere o ID.")
    elif r.status_code == 202:
        st.info("Documento recebido e ainda processando. Tenta buscar de novo em instantes.")
    elif r.status_code != 200:
        st.error(r.json().get("detail", r.text))
    else:
        res = r.json()
        st.caption(f"**Status:** {res.get('status', '-')}")
        exibir_classificacao(res.get("classificacao"))
        if res.get("dados_extraidos") is not None:
            bloco_medico(res.get("dados_extraidos"))
            bloco_diagnostico(res.get("dados_extraidos"))

        d = res.get("decisao_roteamento") or {}
        if d:
            (st.error if d.get("destino_principal") == "Fila_Emergencia_Medica" else
             st.warning if d.get("requer_auditoria_humana") else st.success)(
                f"**Destino: {d.get('destino_principal', '-')}** - "
                f"{d.get('justificativa_roteamento', '')}")
        problemas = res.get("problemas") or []
        if problemas:
            st.subheader("Pontos de atenção")
            for p in problemas:
                st.write(f"- {p}")
