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
        chave = f"medico_{rotulo}"
        # Mesmo padrão de bloco_paciente: o valor vem SÓ do session_state,
        # gravado ANTES de criar o widget, para não reutilizar o médico do
        # documento anterior. Sem value= (senão o Streamlit avisa que o
        # widget tem default e também valor setado via Session State API).
        st.session_state[chave] = valor
        st.text_input(rotulo, disabled=True, key=chave)
