"""H6.1.1 T3 — Página de configuração de regras e limite de confiança."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import requests
import streamlit as st

PASTA_UI = str(Path(__file__).resolve().parents[1])
if PASTA_UI not in sys.path:
    sys.path.insert(0, PASTA_UI)

try:
    from services.estilo import preparar_pagina
except ImportError:
    def preparar_pagina():
        pass

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="Regras de Triagem", layout="wide")
preparar_pagina()

CAMINHO_LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo.png"
if CAMINHO_LOGO.exists():
    st.logo(str(CAMINHO_LOGO), size="large")

# Inicializa sessão da auditora
if "auditora" not in st.session_state:
    st.session_state["auditora"] = "Dra. Renata Silveira"
if "nome_auditora" not in st.session_state:
    st.session_state["nome_auditora"] = st.session_state["auditora"]

st.title("⚙️ Regras de Triagem")
st.subheader("Ajuste do Limite de Confiança (H6.1.1)")

col_auditora, _ = st.columns([1, 2])
with col_auditora:
    nome_auditora = st.text_input(
        "Nome da auditora responsável",
        value=st.session_state.get("auditora", "Dra. Renata Silveira"),
    )
    st.session_state["auditora"] = nome_auditora
    st.session_state["nome_auditora"] = nome_auditora


def carregar_regras() -> dict:
    try:
        r = requests.get(f"{API_URL}/regras", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {
        "limite_confianca": 0.80,
        "versao": "v1",
        "campos_criticos": [
            "paciente.nome",
            "medico_solicitante.crm",
            "medicamentos.nome",
            "medicamentos.dose",
            "cid_sugerido",
        ],
    }


regras_atuais = carregar_regras()
limite_atual = float(regras_atuais.get("limite_confianca", 0.80))
limite_atual = min(0.99, max(0.50, limite_atual))
versao_atual = regras_atuais.get("versao", "v1")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Limite de confiança ativo", f"{limite_atual:.2f}")
with col2:
    st.metric("Versão das regras", versao_atual)
with col3:
    atualizado_em = regras_atuais.get("atualizado_em")
    st.metric(
        "Última alteração",
        regras_atuais.get("atualizado_por") or "Padrão inicial",
        delta=atualizado_em[:19].replace("T", " ") if atualizado_em else None,
    )

st.markdown("---")
st.markdown(
    """
    **Como funciona o limite:**
    Documentos cujo **score global** (menor valor entre classificação e média dos campos)
    ou qualquer **campo crítico** ficar abaixo deste limite são automaticamente
    encaminhados para a **Fila de Revisão Humana**.
    """
)

# Slider exigido por H6.1.1 T3: 0,50 a 0,99 com passo 0,01
novo_limite = st.slider(
    "Score mínimo para roteamento automático",
    min_value=0.50,
    max_value=0.99,
    value=limite_atual,
    step=0.01,
    help="Valores entre 0,50 e 0,99. Documentos com confiança abaixo deste valor vão para revisão humana.",
)

if st.button("Salvar novo limite de confiança", type="primary"):
    try:
        payload = {
            "limite_confianca": novo_limite,
            "auditora": st.session_state.get("auditora", "Auditora"),
        }
        resp = requests.put(f"{API_URL}/regras/limite", json=payload, timeout=5)
        if resp.status_code == 200:
            dados = resp.json()
            st.success(
                f"Limite alterado para {novo_limite:.2f} com sucesso! "
                f"Nova versão gerada: **{dados.get('versao')}**."
            )
            st.rerun()
        else:
            st.error(f"Erro ao salvar: {resp.status_code} - {resp.text}")
    except Exception as e:
        st.error(f"Não foi possível conectar à API: {e}")

st.markdown("---")
with st.expander("Campos Críticos e Parâmetros Ativos"):
    st.write("**Campos críticos avaliados individualmente:**")
    st.json(regras_atuais.get("campos_criticos", []))
    st.write("**Canais de origem aceitos:**")
    st.json(regras_atuais.get("canais_origem", []))
    st.write("**Destinos disponíveis:**")
    st.json(regras_atuais.get("destinos", []))

