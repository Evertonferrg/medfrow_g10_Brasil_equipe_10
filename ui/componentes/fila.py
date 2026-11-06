"""Funções puras da fila de revisão (testáveis sem Streamlit)."""

from __future__ import annotations

from datetime import UTC, datetime

ROTULO_STATUS = {
    "recebido": "Recebido",
    "processando": "Processando",
    "processado": "Processado",
    "em_auditoria_humana": "Em auditoria humana",
    "rejeitado": "Rejeitado",
}


def minutos_de_espera(chegada_em: str | datetime, agora: datetime | None = None) -> int:
    chegada = (
        datetime.fromisoformat(chegada_em)
        if isinstance(chegada_em, str)
        else chegada_em
    )
    if chegada.tzinfo is None:
        chegada = chegada.replace(tzinfo=UTC)
    agora = agora or datetime.now(UTC)
    return max(0, int((agora - chegada).total_seconds() // 60))


def texto_espera(minutos: int) -> str:
    h, m = divmod(minutos, 60)
    return f"{h} h {m} min" if h else f"{m} min"


def texto_dose_destacada(destaque: dict) -> str:
    # texto além da cor, para não depender só do vermelho
    return f"⚠️ DOSE FORA DA FAIXA: {destaque['medicamento']} {destaque['dose']}"
