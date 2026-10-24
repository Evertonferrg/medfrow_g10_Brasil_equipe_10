"""T4 — tela de resultado: consulta GET /documentos/{documento_id} e mostra
o tipo identificado e a especialidade provável ao analista."""
import os

import requests
import streamlit as st

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
        cl = res.get("classificacao")
        if cl:
            a, b = st.columns(2)
            a.metric("Tipo do documento", cl.get("tipo_documento") or "—")
            b.metric("Especialidade provável", cl.get("especialidade") or "—")
            c, d = st.columns(2)
            c.metric("Prioridade", cl.get("nivel_prioridade") or "—")
            d.metric("Confiança", cl.get("score_confianca_classificacao", "—"))
        else:
            st.warning("Sem classificação: o documento foi para revisão humana.")

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
