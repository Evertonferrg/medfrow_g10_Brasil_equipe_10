"""H3.4.1 T4 — trecho para colar em ui/pages/6_Fila_revisao.py (ou onde a fila
de emergência é desenhada), dentro do loop de itens.

O id vai em st.query_params (link compartilhável) e também em session_state,
porque a troca de página pode limpar os parâmetros da URL em algumas versões.
"""

import streamlit as st


def botao_abrir_caso(documento_id: str) -> None:
    if st.button("Abrir caso", key=f"abrir_{documento_id}"):
        st.session_state["caso_id"] = documento_id
        st.query_params["id"] = documento_id
        st.switch_page("pages/5_Caso.py")
