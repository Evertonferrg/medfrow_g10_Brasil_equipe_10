import streamlit as st

AUSENTE = "—"


def formatar_cid(cid: str | None, origem: str | None = None) -> str:
    if not cid:
        return AUSENTE
    if origem == "sugerido":
        return f"{cid} (sugerido)"
    return cid


def resumo_diagnostico(dados_extraidos: dict | None) -> dict[str, str]:
    d = dados_extraidos or {}
    origem = d.get("origem_cid") or d.get("cid_origem")
    return {
        "Diagnóstico principal": d.get("diagnostico_principal") or AUSENTE,
        "CID-10": formatar_cid(d.get("cid_sugerido"), origem),
    }


def bloco_diagnostico(dados_extraidos: dict | None) -> None:
    st.subheader("Diagnóstico e CID-10")
    resumo = resumo_diagnostico(dados_extraidos)
    for rotulo, valor in resumo.items():
        st.text_input(rotulo, value=valor, disabled=True, key=f"diagnostico_{rotulo}")
