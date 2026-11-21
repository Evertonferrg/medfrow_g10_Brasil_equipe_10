"""H4.2.1 T2 + H4.2.2 T2 — fila de revisão.
Requer Streamlit >= 1.37 (st.fragment).
"""

import html
import os
import sys
from pathlib import Path

import requests
import streamlit as st

RAIZ_UI = Path(__file__).resolve().parents[1]
if str(RAIZ_UI) not in sys.path:
    sys.path.insert(0, str(RAIZ_UI))

from componentes.fila import (
    minutos_de_espera,
    texto_dose_destacada,
    texto_espera,
)
from services.estilo import pill, preparar_pagina
from services.navegacao import abrir_caso, abrir_revisao

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Fila de Revisão", layout="wide")
preparar_pagina()  # logo, menu lateral e estilo padrão

st.title("Fila de Revisão")

# Cor da faixa e da pílula conforme a prioridade do caso
COR_PRIORIDADE = {
    "urgente": "red",
    "emergência": "red",
    "emergencia": "red",
    "alta": "orange",
    "rotina": "green",
    "baixa": "green",
}


def cor_prioridade(prioridade) -> str:
    return COR_PRIORIDADE.get(str(prioridade or "").strip().lower(), "gray")


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
        f"{len(casos)} documento(s) pendente(s), do mais urgente ao menos urgente."
    )

    for caso in casos:
        documento_id = caso["documento_id"]
        cor = cor_prioridade(caso["prioridade"])
        chegada_bruta = str(caso.get("chegada_em") or "")
        sem_data = not chegada_bruta or chegada_bruta.startswith("1970-01-01")
        if sem_data:
            meta_tempo = "data de chegada não registrada"
        else:
            espera = texto_espera(minutos_de_espera(chegada_bruta))
            chegada = chegada_bruta[:16].replace("T", " ")
            meta_tempo = (
                f"chegou em {html.escape(chegada)} · "
                f"aguardando há {html.escape(str(espera))}"
            )

        with st.container(key=f"card_fila_{cor}_{documento_id}"):
            info, acao = st.columns([4, 1.4], vertical_alignment="top")

            with info:
                st.markdown(
                    '<div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.25rem">'
                    f'<span style="font-size:1.05rem;font-weight:700">{html.escape(str(caso["tipo"]))}</span>'
                    f"{pill(html.escape(str(caso['prioridade'])), cor)}</div>"
                    '<p style="margin:0 0 .6rem;font-size:.85rem;opacity:.75">'
                    f"Documento <code>{html.escape(str(documento_id))}</code> · "
                    f"{meta_tempo}</p>",
                    unsafe_allow_html=True,
                )

                st.write("Motivos da dúvida:")

                for motivo in caso["motivos"]:
                    st.markdown(f"- {motivo}")

                for destaque in caso.get("destaques_dose", []):
                    st.markdown(f":red[**{texto_dose_destacada(destaque)}**]")

            with acao:
                # Principal: vai direto à tela de decisão da auditora
                if st.button(
                    "Revisar agora",
                    key=f"revisar_{documento_id}",
                    type="primary",
                    icon=":material/open_in_new:",
                    width="stretch",
                ):
                    abrir_revisao(documento_id)

                # Secundário: entender o caso no Dashboard antes de decidir
                with st.container(key=f"fila_abrir_{documento_id}"):
                    if st.button(
                        "Abrir caso",
                        key=f"abrir_{documento_id}",
                        icon=":material/open_in_new:",
                        width="stretch",
                    ):
                        abrir_caso(documento_id)


fila()
