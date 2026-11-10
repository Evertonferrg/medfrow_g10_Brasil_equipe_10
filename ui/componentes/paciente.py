"""H1.3.1 T3 — Bloco "Paciente" da tela de resultado.

Fica num arquivo próprio (e não dentro de ui/pages/2_Triagem.py) para não gerar
conflito com quem cria a página de resultado (H1.2.1 T4). A página só precisa de:

    from componentes.paciente import bloco_paciente
    ...
    bloco_paciente(resultado.get("dados_extraidos"))

Os valores vêm de documentos clínicos, então são exibidos como texto puro (campo
desabilitado), nunca como Markdown/HTML.
"""

import streamlit as st

AUSENTE = "—"


def resumo_paciente(paciente: dict | None) -> dict[str, str]:
    """Nome, idade e data de nacimento prontos para exibir("-" quando não há)."""
    p = paciente or {}
    idade = p.get("idade")
    return {
        "Nome": p.get("nome") or AUSENTE,
        "Idade": f"{idade} anos" if idade is not None else AUSENTE,
        "Data de nascimento": p.get("data_nascimento") or AUSENTE,
    }


def bloco_paciente(dados_extraidos: dict | None) -> None:
    st.subheader("Paciente")
    resumo = resumo_paciente((dados_extraidos or {}).get("paciente"))
    for rotulo, valor in resumo.items():
        chave = f"paciente_{rotulo}"
        # O valor vem SÓ do session_state, gravado ANTES de criar o widget:
        # é ele que manda quando a chave já existe, então a tela mostra o
        # paciente do documento atual e não o da consulta anterior.
        # Não passar value=: com value= E session_state o Streamlit avisa
        # "widget created with a default value but also had its value set
        # via the Session State API".
        st.session_state[chave] = valor
        st.text_input(rotulo, disabled=True, key=chave)
