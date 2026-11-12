"""H4.3.1 / H4.3.2 — painel de revisão: original à esquerda, extração à direita.

Aberto a partir da fila: /Revisao_caso?id=<documento_id>. Somente leitura
(a edição chega em H4.4.2). Requer PyMuPDF para renderizar PDF.
"""

import os
import sys
from pathlib import Path

import requests
import streamlit as st
from services.estilo import preparar_pagina

PASTA_UI = str(Path(__file__).resolve().parents[1])
if PASTA_UI not in sys.path:
    sys.path.insert(0, PASTA_UI)

from componentes.revisao import (
    LIMITE_PADRAO,
    campo_revisao,
    campos_inconsistentes,
    evidencia_do_campo,
)

API = os.getenv("API_URL", "http://localhost:8000")
MAX_PAGINAS = 10


def limite_confianca() -> float:
    try:
        from componentes.classificacao import carregar_limite_confianca

        return float(carregar_limite_confianca())
    except (ImportError, OSError, KeyError, TypeError, ValueError):
        return LIMITE_PADRAO


def mostrar_original(documento_id: str) -> None:
    try:
        r = requests.get(f"{API}/documentos/{documento_id}/original", timeout=30)
    except requests.RequestException:
        st.error("Não consegui buscar o original agora.")
        return
    if r.status_code == 404:
        st.warning("Original não encontrado.")
        return
    if r.status_code != 200:
        st.error("Não foi possível abrir o original.")
        return
    tipo = r.headers.get("content-type", "")
    if tipo.startswith("text/"):
        st.text(r.content.decode("utf-8", errors="replace"))
    elif tipo.startswith("image/"):
        st.image(r.content)
    elif tipo.startswith("application/pdf"):
        try:
            import fitz  # PyMuPDF
        except ImportError:
            st.error("Instale o PyMuPDF (pymupdf) para ver PDFs.")
            return
        with fitz.open(stream=r.content, filetype="pdf") as pdf:
            for i, pagina in enumerate(pdf):
                if i >= MAX_PAGINAS:
                    st.caption(f"Mostrando as {MAX_PAGINAS} primeiras páginas.")
                    break
                st.image(pagina.get_pixmap(dpi=100).tobytes("png"))
    else:
        st.info("Formato sem visualização no painel.")


def mostrar_extracao(res: dict) -> None:
    dados = res.get("dados_extraidos") or {}
    cl = res.get("classificacao") or {}
    score = cl.get(
        "score_confianca_classificacao"
    )  # só há score do documento, não por campo
    limite = limite_confianca()
    ruins = campos_inconsistentes(res.get("problemas"))
    pac = dados.get("paciente") or {}
    med = dados.get("medico_solicitante") or {}

    def campo(rotulo, valor, chave, ident, *nomes):
        campo_revisao(
            rotulo,
            valor,
            chave=f"rev_{chave}",
            score=score,
            inconsistente=ident in ruins,
            limite=limite,
            evidencia=evidencia_do_campo(dados, *nomes),
        )

    st.caption(
        f"Tipo: {cl.get('tipo_documento') or '—'} · confiança {score} (limite {limite})"
    )
    st.subheader("Paciente")
    campo("Nome", pac.get("nome"), "pac_nome", "nome", "nome_paciente", "paciente.nome")
    campo("Idade", pac.get("idade"), "pac_idade", "idade", "idade", "paciente.idade")
    campo(
        "Data de nascimento",
        pac.get("data_nascimento"),
        "pac_nasc",
        "data_nascimento",
        "data_nascimento",
    )
    st.subheader("Médico solicitante")
    campo("Nome", med.get("nome"), "med_nome", "medico", "medico_solicitante.nome")
    campo("CRM", med.get("crm"), "med_crm", "crm", "crm", "medico_solicitante.crm")
    st.subheader("Diagnóstico")
    campo(
        "Diagnóstico principal",
        dados.get("diagnostico_principal"),
        "diag",
        "diagnostico",
        "diagnostico_principal",
    )
    campo(
        "CID",
        dados.get("cid_sugerido") or dados.get("cid"),
        "cid",
        "cid",
        "cid",
        "cid_sugerido",
    )
    meds = dados.get("medicamentos") or []
    if meds:
        st.subheader("Medicamentos")
        st.dataframe(
            [
                {
                    "Medicamento": m.get("nome") or "—",
                    "Dose": m.get("dose") or "—",
                    "Via": m.get("via") or "—",
                }
                for m in meds
            ],
            hide_index=True,
        )
    if res.get("problemas"):
        st.subheader("⚠️ Pontos de atenção")
        for p in res["problemas"]:
            st.write(f"- {p}")


st.set_page_config(
    page_title="MediFlow — Revisão do caso", page_icon="🧐", layout="wide"
)
preparar_pagina()
st.title("🧐 Revisão do caso")

documento_id = str(st.query_params.get("id", "")).strip()
if not documento_id:
    st.info("Abra um caso pela fila de revisão (a URL precisa de ?id=...).")
    st.stop()

st.caption(f"Documento: {documento_id}")
try:
    resp = requests.get(f"{API}/documentos/{documento_id}", timeout=30)
except requests.RequestException:
    st.error("Não consegui falar com a API.")
    st.stop()
if resp.status_code != 200:
    st.warning("Resultado indisponível para este documento.")
    st.stop()

esquerda, direita = st.columns(2)
with esquerda:
    st.subheader("Original")
    mostrar_original(documento_id)
with direita:
    st.subheader("Extração")
    mostrar_extracao(resp.json())
