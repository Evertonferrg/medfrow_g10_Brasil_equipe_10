
"""H4.2.1 T2 + H4.2.2 T2 — fila de revisão.
Requer Streamlit >= 1.37 (st.fragment).
"""

import os
from pathlib import Path

import requests
import streamlit as st
from services.estilo import preparar_pagina
from ui.componentes.fila import (
    minutos_de_espera,
    texto_dose_destacada,
    texto_espera,
)
from ui.fila_abrir_caso_snippet import botao_abrir_caso


API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Fila de revisão", layout="wide")
preparar_pagina()

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

st.title("Fila de revisão")


@st.fragment(run_every=30)
def fila():
    try:
        resposta = requests.get(
            f"{API_URL}/filas/revisao",
            timeout=5,
        )
        resposta.raise_for_status()
        casos = resposta.json()

    except requests.RequestException as erro:
        st.error(
            f"Não foi possível carregar a fila. "
            f"Tente novamente em instantes. Detalhe: {erro}"
        )
        return

    if not casos:
        st.info("Nenhum documento aguardando revisão.")
        return

    st.caption(
        f"{len(casos)} documento(s) pendente(s), "
        "do mais urgente ao menos urgente."
    )

    for caso in casos:
        documento_id = caso["documento_id"]

        with st.container(border=True):
            st.markdown(
                f"**{caso['tipo']}** — "
                f"prioridade **{caso['prioridade']}** — "
                f"documento `{documento_id}`"
            )

            espera = texto_espera(
                minutos_de_espera(caso["chegada_em"])
            )

            st.write(
                f"Chegou em "
                f"{caso['chegada_em'][:16].replace('T', ' ')} "
                f"· aguardando há {espera}"
            )

            st.write("Motivos da dúvida:")

            for motivo in caso["motivos"]:
                st.markdown(f"- {motivo}")

            for destaque in caso.get("destaques_dose", []):
                st.markdown(
                    f":red[**{texto_dose_destacada(destaque)}**]"
                )

            # Abre a tela resumida do caso
            botao_abrir_caso(documento_id)


fila()
