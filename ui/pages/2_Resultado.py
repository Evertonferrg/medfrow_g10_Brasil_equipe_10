"""H2.1.1 T5 — Tela de resultado: consulta GET /documentos/{documento_id} e exibe
o destino de roteamento em destaque, acima dos dados extraídos clínicos.
"""
import json
"""T4 — tela de resultado: consulta GET /documentos/{documento_id} e mostra
o tipo identificado, o score de confiança ao lado do tipo e a especialidade provável ao analista."""
import os
import sys
from pathlib import Path

import requests
import streamlit as st

RAIZ_UI = Path(__file__).resolve().parents[1]
if str(RAIZ_UI) not in sys.path:
    sys.path.insert(0, str(RAIZ_UI))

try:
    from componentes.paciente import bloco_paciente
except ImportError:
    bloco_paciente = None
PASTA_UI = str(Path(__file__).resolve().parents[1])
if PASTA_UI not in sys.path:
    sys.path.insert(0, PASTA_UI)

from componentes.classificacao import (  # noqa: F401
    carregar_limite_confianca,
    exibir_classificacao,
    formatar_confianca,
)
from componentes.diagnostico import bloco_diagnostico
from componentes.medico import bloco_medico

API = os.getenv("API_URL", "http://localhost:8000")


def mostrar_medicamentos(dados, tipo_documento=None):
    """H1.3.4 T4: tabela de medicamentos e posologia."""
    itens = (dados or {}).get("medicamentos") or []
    if not itens:
        if tipo_documento == "Receituário Médico":
            st.subheader("Medicamentos")
            st.caption("Nenhum medicamento identificado nesta receita.")
        return
    st.subheader("Medicamentos")
    st.dataframe(
        [
            {
                "Medicamento": m.get("nome") or "—",
                "Dose": m.get("dose") or "—",
                "Via": m.get("via") or "—",
                "Frequência": m.get("frequencia") or "—",
                "Duração": m.get("duracao") or "—",
            }
            for m in itens
        ],
        hide_index=True,
    )
    if any(not m.get("dose") for m in itens):
        st.caption(
            "⚠ Há medicamento sem dose informada no documento (veja os pontos de atenção)."
        )


def mostrar_exames(dados):
    """H1.3.5 T5: exames e procedimentos, com o código TUSS ao lado."""
    itens = (dados or {}).get("exames") or []
    if not itens:
        return
    st.subheader("Exames e procedimentos")
    st.dataframe(
        [
            {"Exame": e.get("nome") or "—", "Código TUSS": e.get("codigo_tuss") or "—"}
            for e in itens
        ],
        hide_index=True,
    )


def mostrar_destino(decisao):
    """H2.2.1 T4: o destino em destaque e, logo abaixo, a justificativa e a regra aplicada."""
    destino = decisao.get("destino_principal", "-")
    (
        st.error
        if destino == "Fila_Emergencia_Medica"
        else st.warning
        if decisao.get("requer_auditoria_humana")
        else st.success
    )(f"**Destino: {destino}**")
    if decisao.get("justificativa_roteamento"):
        st.markdown(f"**Por quê?** {decisao['justificativa_roteamento']}")
    if decisao.get("regra_aplicada"):
        st.caption(f"Regra aplicada: {decisao['regra_aplicada']}")


def botao_download(resultado):
    """H2.3.1 T4: baixa o resultado exatamente como a API devolveu (formato combinado)."""
    nome = f"{resultado.get('documento_id') or 'resultado'}.json"
    st.download_button(
        "⬇️ Baixar resultado (JSON)",
        data=json.dumps(resultado, ensure_ascii=False, indent=2),
        file_name=nome,
        mime="application/json",
    )


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
        st.info(
            "Documento recebido e ainda processando. Tenta buscar de novo em instantes."
        )
    elif r.status_code != 200:
        st.error(r.json().get("detail", r.text))
    else:
        res = r.json()
        st.caption(f"**ID:** {res.get('documento_id', doc_id)} | **Status:** {res.get('status', '-')}")

        # H2.1.1 T5: Destino em grande destaque na página, acima dos dados extraídos
        d = res.get("decisao_roteamento") or {}
        destino = d.get("destino_principal", "—")
        justificativa = d.get("justificativa_roteamento", "")
        requer_auditoria = d.get("requer_auditoria_humana", False)

        if destino == "Fila_Emergencia_Medica":
            st.error(f"### 🚨 Destino: {destino}\n\n{justificativa}")
        elif requer_auditoria or destino == "Fila_Revisao_Humana":
            st.warning(f"### ⚠️ Destino: {destino}\n\n{justificativa}")
        elif destino == "Farmacia_Hospitalar":
            st.success(f"### 💊 Destino: {destino}\n\n{justificativa}")
        else:
            st.success(f"### 📋 Destino: {destino}\n\n{justificativa}")

        notificacao = d.get("notificacao_gerada")
        if notificacao:
            st.info(f"📢 **Notificação ({notificacao.get('canal', 'Alerta')}):** {notificacao.get('mensagem', '')}")

        # Classificação clínica
        cl = res.get("classificacao")
        if cl:
            st.markdown("#### Classificação")
            a, b, c, e = st.columns(4)
            a.metric("Tipo do documento", cl.get("tipo_documento") or "—")
            b.metric("Especialidade", cl.get("especialidade") or "—")
            c.metric("Prioridade", cl.get("nivel_prioridade") or "—")
            e.metric("Confiança", cl.get("score_confianca_classificacao", "—"))
        else:
            st.warning("Sem classificação automática: o documento requer revisão humana.")
        st.caption(f"**Status:** {res.get('status', '-')}")
        exibir_classificacao(res.get("classificacao"))
        if res.get("dados_extraidos") is not None:
            bloco_medico(res.get("dados_extraidos"))
            bloco_diagnostico(res.get("dados_extraidos"))

        d = res.get("decisao_roteamento") or {}
        if d:
            mostrar_destino(d)
        problemas = res.get("problemas") or []
        if problemas:
            st.subheader("Pontos de atenção")

        # Chamada adicionada para exibir a tabela e avisos de medicamentos
        cl = res.get("classificacao") or {}
        mostrar_medicamentos(res.get("dados_extraidos"), cl.get("tipo_documento"))

        # Exames e procedimentos, com o código TUSS ao lado
        mostrar_exames(res.get("dados_extraidos"))

        botao_download(res)
