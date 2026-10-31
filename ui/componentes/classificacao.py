import json
import os
from pathlib import Path

import streamlit as st

ARQUIVO_REGRAS = Path(__file__).resolve().parents[2] / "config" / "regras.json"
LIMITE_CONFIANCA_PADRAO = 0.80


def carregar_limite_confianca() -> float:
    bruto = os.getenv("LIMIAR_CONFIANCA")
    if bruto is None:
        try:
            dados = json.loads(ARQUIVO_REGRAS.read_text(encoding="utf-8"))
            bruto = dados.get("limite_confianca", LIMITE_CONFIANCA_PADRAO)
        except (OSError, ValueError, AttributeError):
            bruto = LIMITE_CONFIANCA_PADRAO
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        return LIMITE_CONFIANCA_PADRAO
    return min(1.0, max(0.0, valor))


def formatar_confianca(score: float | None, limite: float | None = None) -> str:
    if score is None or isinstance(score, bool) or not isinstance(score, (int, float)):
        return "—"
    lim = carregar_limite_confianca() if limite is None else limite
    if score < lim:
        return f"⚠️ {score:.2f} (abaixo do limite)"
    return f"{score:.2f}"


def exibir_classificacao(cl: dict | None, limite: float | None = None) -> None:
    if not cl:
        st.warning("Sem classificação: o documento foi para revisão humana.")
        return
    lim = carregar_limite_confianca() if limite is None else limite
    score = cl.get("score_confianca_classificacao")
    a, b = st.columns(2)
    a.metric("Tipo do documento", cl.get("tipo_documento") or "—")
    b.metric("Confiança", formatar_confianca(score, lim))
    c, d = st.columns(2)
    c.metric("Especialidade provável", cl.get("especialidade") or "—")
    d.metric("Prioridade", cl.get("nivel_prioridade") or "—")
    if isinstance(score, (int, float)) and not isinstance(score, bool) and score < lim:
        st.warning(
            f"⚠️ Confiança {score:.2f} abaixo do limite ({lim:.2f}): "
            "documento retido para revisão humana."
        )
