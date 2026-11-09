"""H4.3.2 — destaque dos campos duvidosos no painel de revisão.

Funções puras (precisa_destaque, motivo_destaque, campos_inconsistentes,
evidencia_do_campo) ficam testáveis sem Streamlit; campo_revisao é a parte visual.
"""

from __future__ import annotations

LIMITE_PADRAO = 0.8
_SINAIS = (
    "inconsist",
    "inválid",
    "invalid",
    "diverge",
    "faltante",
    "ausente",
    "não encontrado",
)
_CAMPOS = {  # palavra no motivo -> campo do painel
    "crm": "crm",
    "idade": "idade",
    "nascimento": "data_nascimento",
    "cid": "cid",
    "diagnóstico": "diagnostico",
    "nome do paciente": "nome",
    "nome_paciente": "nome",
}


def precisa_destaque(score: float | None, inconsistente: bool, limite: float) -> bool:
    """T1: destaca se o campo é inconsistente ou se o score está ABAIXO do limite
    (score igual ao limite não destaca)."""
    return bool(inconsistente) or (score is not None and score < limite)


def motivo_destaque(
    score: float | None, inconsistente: bool, limite: float
) -> str | None:
    if inconsistente:
        return "inconsistente"
    if score is not None and score < limite:
        return f"abaixo do limite ({score:.2f})"
    return None


def campos_inconsistentes(problemas: list[str] | None) -> set[str]:
    """Heurística: um problema com palavra de alerta que cita um campo marca esse campo.
    O resultado da triagem não traz o campo de cada problema, só o texto."""
    achados = set()
    for problema in problemas or []:
        texto = str(problema).lower()
        if not any(sinal in texto for sinal in _SINAIS):
            continue
        achados.update(campo for palavra, campo in _CAMPOS.items() if palavra in texto)
    return achados


def evidencia_do_campo(dados: dict | None, *nomes: str) -> str | None:
    """Trecho do original de onde o campo veio (dados_extraidos['evidencias'])."""
    for ev in (dados or {}).get("evidencias") or []:
        if isinstance(ev, dict) and ev.get("campo") in nomes and ev.get("trecho"):
            return str(ev["trecho"])
    return None


def campo_revisao(
    rotulo: str,
    valor,
    *,
    chave: str,
    score: float | None = None,
    inconsistente: bool = False,
    limite: float = LIMITE_PADRAO,
    evidencia: str | None = None,
) -> None:
    """T2: valor em st.text_input desabilitado; help= mostra a evidência ao passar o cursor.
    Quando precisa de destaque, mostra ícone e o motivo em texto (não só cor)."""
    import streamlit as st

    texto = "—" if valor in (None, "") else str(valor)
    st.text_input(rotulo, value=texto, disabled=True, help=evidencia or None, key=chave)
    motivo = motivo_destaque(score, inconsistente, limite)
    if motivo:
        st.caption(f"⚠️ {rotulo}: {motivo}")
