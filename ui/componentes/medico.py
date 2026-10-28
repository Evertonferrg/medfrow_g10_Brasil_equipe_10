import streamlit as st

AUSENTE = "—"


def resumo_medico(medico: dict | None) -> dict[str, str]:
    m = medico or {}
    return {
        "Nome": m.get("nome") or AUSENTE,
        "CRM": m.get("crm") or AUSENTE,
    }


def bloco_medico(dados_extraidos: dict | None) -> None:
    st.subheader("Médico solicitante")
    resumo = resumo_medico((dados_extraidos or {}).get("medico_solicitante"))
    for rotulo, valor in resumo.items():
        st.text_input(rotulo, value=valor, disabled=True, key=f"medico_{rotulo}")
