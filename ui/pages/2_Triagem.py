import json

_ = """T4 — tela de resultado: consulta GET /documentos/{documento_id} e mostra
o tipo identificado, o score de confiança ao lado do tipo e a especialidade provável ao analista.
"""

_ = """H2.1.1 T5 — Tela de resultado: consulta GET /documentos/{documento_id} e exibe
o destino de roteamento em destaque, acima dos dados extraídos clínicos.
"""
import os
import sys
from pathlib import Path

import requests
import streamlit as st

PASTA_UI = str(Path(__file__).resolve().parents[1])
if PASTA_UI not in sys.path:
    sys.path.insert(0, PASTA_UI)


from componentes.classificacao import (  # noqa: F401
    carregar_limite_confianca,
    exibir_classificacao,
    formatar_confianca,
)
from componentes.fila import ROTULO_STATUS  # H2.3.2 T5

try:
    from componentes.historico import exibir_linha_do_tempo  # H5.2.2 T4
except ImportError:
    exibir_linha_do_tempo = None

try:
    from componentes.paciente import bloco_paciente
except ImportError:
    bloco_paciente = None

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
    """H1.3.5 T5 / H2.1.2: exames e procedimentos, com o código TUSS ao lado."""
    itens = (dados or {}).get("exames") or (dados or {}).get("exames_solicitados") or []
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

CAMINHO_LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo.png"
if CAMINHO_LOGO.exists():
    st.logo(str(CAMINHO_LOGO), size="large")

st.markdown(
    """
<style>
    [data-testid="stLogo"] {
        height: 3.5rem !important;
    }
    [data-testid="stLogo"] img {
        height: 3.5rem !important;
        max-height: 3.5rem !important;
        width: auto !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("<div style='height: 35vh;'></div>", unsafe_allow_html=True)
    st.divider()
    st.caption("⚙️ Configurações")
    st.caption("🚪 Sair")

st.title("🔎 Resultado da triagem")

# Suporte a consulta direta via URL: ?id=DOC-... ou ?documento_id=DOC-...
param_id = str(st.query_params.get("id") or st.query_params.get("documento_id") or "").strip()

with st.form("consulta"):
    doc_id = st.text_input(
        "ID do documento",
        value=param_id if param_id else "",
        placeholder="DOC-CLIN-2026-8942",
    )
    buscar = st.form_submit_button("Buscar resultado")

deve_buscar = (buscar and doc_id.strip()) or (param_id and not buscar)
id_para_busca = doc_id.strip() if doc_id.strip() else param_id

if deve_buscar and id_para_busca:
    try:
        r = requests.get(f"{API}/documentos/{id_para_busca}", timeout=30)
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
        status_doc = res.get(
            "status_documento"
        )  # H2.3.2 T5: estágio do documento em destaque
        if status_doc:
            st.subheader(
                f"Status do documento: {ROTULO_STATUS.get(status_doc, status_doc)}"
            )
        st.caption(f"**Status:** {res.get('status', '-')}")
        cl = res.get("classificacao")
        if cl:
            # H1.2.2: usa o componente de classificação, que mostra o score
            # formatado (ex.: "0.95") e, abaixo do limite, o aviso
            # "⚠️ 0.60 (abaixo do limite)" com o banner de retenção.
            exibir_classificacao(cl)
        else:
            st.warning("Sem classificação: o documento foi para revisão humana.")
        decisao = res.get("decisao_roteamento") or {}
        mostrar_destino(decisao)

        # Dados Extraídos (H1.3.1, H1.3.4, H1.3.5)
        dados = res.get("dados_extraidos") or {}
        if dados:
            st.markdown("---")
            st.markdown("### 📋 Dados Clínicos Extraídos")

            col_paciente, col_medico = st.columns(2)
            with col_paciente:
                if bloco_paciente:
                    bloco_paciente(dados)
                else:
                    st.subheader("Paciente")
                    st.json(dados.get("paciente", {}))

            with col_medico:
                st.subheader("Médico solicitante")
                med = dados.get("medico_solicitante") or {}
                # O valor vem SÓ do session_state, gravado ANTES de criar os
                # widgets: é ele que manda quando a chave já existe, então a
                # tela mostra o médico/CRM do documento atual e não os da
                # consulta anterior. Sem value=: com value= E session_state o
                # Streamlit avisa "widget created with a default value but
                # also had its value set via the Session State API".
                st.session_state["medico_nome"] = med.get("nome") or "—"
                st.session_state["medico_crm"] = med.get("crm") or "—"
                st.text_input("Nome", disabled=True, key="medico_nome")
                st.text_input("CRM", disabled=True, key="medico_crm")

            diag = dados.get("diagnostico_principal")
            cid = dados.get("cid_sugerido") or dados.get("cid")
            cid_origem = dados.get("cid_origem") or dados.get("origem_cid")
            if diag or cid:
                st.markdown(f"**Diagnóstico:** {diag or '—'}")
                st.markdown(
                    f"**CID:** {cid or '—'} ({cid_origem or 'não especificado'})"
                )

        # Medicamentos estruturados (H1.3.4 / H2.1.1)
        tipo_documento = (cl or {}).get("tipo_documento")
        mostrar_medicamentos(dados, tipo_documento)
        mostrar_exames(dados)

        # Problemas identificados / pontos de atenção
        problemas = res.get("problemas") or []
        if problemas:
            st.subheader("⚠️ Pontos de atenção")
            for p in problemas:
                st.write(f"- {p}")

        # H5.2.2 T4: Linha do tempo / histórico do documento
        if exibir_linha_do_tempo:
            try:
                r_hist = requests.get(f"{API}/documentos/{doc_id.strip()}/historico", timeout=10)
                if getattr(r_hist, "status_code", None) == 200:
                    dados_hist = r_hist.json()
                    if isinstance(dados_hist, list) and (not dados_hist or isinstance(dados_hist[0], dict)):
                        st.markdown("---")
                        exibir_linha_do_tempo(dados_hist)
            except Exception:
                pass

        st.download_button(
            "Baixar resultado (JSON)",
            json.dumps(res, ensure_ascii=False, indent=2),
            file_name=f"{res.get('documento_id', doc_id)}.json",
            mime="application/json",
        )
