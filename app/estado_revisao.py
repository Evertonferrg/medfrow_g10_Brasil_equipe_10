"""H4.4.1 T2 — estado guardado ao enviar um caso à revisão.

Fica em auditoria_humana/<id>.estado.json, ao lado do resultado,
e é apagado na decisão.

Guarda somente o necessário para recalcular o destino:
extração, classificação, limite de confiança e destino calculado,
ignorando os motivos de revisão.
"""

from __future__ import annotations

import logging
from typing import Any

from app.revisao import PASTA_REVISAO, SUFIXO_ESTADO

logger = logging.getLogger(__name__)


def _como_dict(objeto: Any) -> dict | None:
    """Converte objetos de extração ou classificação em dicionários."""
    if objeto is None:
        return None

    if hasattr(objeto, "model_dump"):
        return objeto.model_dump(mode="json")

    return dict(objeto) if isinstance(objeto, dict) else None


def montar_estado_revisao(estado: dict) -> dict:
    """Monta somente os dados necessários para a decisão da auditora."""
    return {
        "destino_calculado": estado.get("destino_calculado"),
        "limite_confianca": estado.get("limite_confianca"),
        "extracao": _como_dict(estado.get("extracao")),
        "classificacao": _como_dict(estado.get("classificacao")),
    }


def salvar_estado_revisao(
    documento_id: str,
    estado: dict,
    armazenamento,
) -> None:
    """Salva o estado junto ao documento enviado para revisão humana.

    Uma falha ao salvar o estado não interrompe o processamento.
    """
    try:
        armazenamento.salvar(
            f"{PASTA_REVISAO}/{documento_id}{SUFIXO_ESTADO}",
            montar_estado_revisao(estado),
        )
    except (OSError, ValueError):
        logger.exception("Não foi possível guardar o estado da revisão")
