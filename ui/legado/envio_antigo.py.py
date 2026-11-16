import json
import os
import uuid

import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="MedFlow", page_icon="🏥", layout="wide")
st.title("🏥 MediFlow — Triagem de documentos clínicos")

with st.form("envio"):
    c1, c2 = st.columns(2)
    doc_id = c1.text_input(
        "ID do documento", value=f"DOC-{uuid.uuid4().hex[:8].upper()}"
    )
    canal = c2.selectbox(
        "Canal de origem", ["Pronto_Socorro", "Ambulatorio", "Laboratorio", "Operadora"]
    )
    texto = st.text_area("Texto do documento", height=180)
    pdf = st.file_uploader("ou envie um PDF digital", type=["pdf"])
    enviar = st.form_submit_button("Enviar para triagem")

if enviar:
    try:
        if pdf is not None:
            r = requests.post(
                f"{API}/triagem/pdf",
                params={"aguardar": "true"},
                data={"documento_id": doc_id, "canal_origem": canal},
                files={"arquivo": (pdf.name, pdf.getvalue(), "application/pdf")},
                timeout=120,
            )
        else:
            r = requests.post(
                f"{API}/triagem",
                params={"aguardar": "true"},
                timeout=120,
                json={
                    "documento_id": doc_id,
                    "tipo_arquivo": "TEXTO",
                    "documento_texto": texto,
                    "canal_origem": canal,
                },
            )
    except requests.RequestException as e:
        st.error(f"Não consegui falar com a API: {e}")
        st.stop()

    if r.status_code != 200:
        st.error(r.json().get("detail", r.text))
        st.stop()

    res = r.json()
    d = res["decisao_roteamento"]
    (
        st.error
        if d["destino_principal"] == "Fila_Emergencia_Medica"
        else st.warning
        if d["requer_auditoria_humana"]
        else st.success
    )(f"**Destino: {d['destino_principal']}** - {d['justificativa_roteamento']}")
    if d.get("notificacao_gerada"):
        st.info(f"Aviso {d['notificacao_gerada']['mensagem']}")

    cl = res.get("classificacao")
    if cl:
        score = cl.get("score_confianca_classificacao")
        limite = float(os.getenv("LIMIAR_CONFIANCA", "0.80"))
        score_txt = (
            f"⚠️ {score:.2f} (abaixo do limite)"
            if isinstance(score, (int, float)) and score < limite
            else f"{score:.2f}"
            if isinstance(score, (int, float))
            else "—"
        )
        a, b, c, e = st.columns(4)
        a.metric("Tipo", cl["tipo_documento"])
        b.metric("Confiança", score_txt)
        c.metric("Especialidade", cl.get("especialidade") or "—")
        e.metric("Prioridade", cl["nivel_prioridade"])
        if cl.get("tipo_documento") == "Não identificado":
            st.warning(
                "Documento fora das categorias clínicas (Não identificado): "
                "o documento foi separado para revisão humana."
            )
    dados = res.get("dados_extraidos") or {}
    if dados:
        a, b = st.columns(2)
        a.subheader("Paciente")
        a.json(dados["paciente"])
        b.subheader("Médico solicitante")
        b.json(dados["medico_solicitante"])
        st.write(
            f"**Diagnóstico** {dados.get('diagnostico_principal') or '-'} "
            f"| **CID:** {dados.get('cid_sugerido') or '-'} ({dados.get('cid_origem') or '-'})"
        )
        if dados.get("medicamentos"):
            st.subheader("Medicamentos")
            st.table(dados["medicamentos"])
        if dados.get("exames"):
            st.subheader("Exames / procedimentos")
            st.table(dados["exames"])
    if res["problemas"]:
        st.subheader("Pontos de atenção")
        for p in res["problemas"]:
            st.write(f"- {p}")
    st.download_button(
        "Baixar resultado (JSON)",
        json.dumps(res, ensure_ascii=False, indent=2),
        file_name=f"{res['documento_id']}.json",
        mime="application/json",
    )
