"""Liga a fila de revisão e a trilha ao app.

O endpoint GET /documentos/{documento_id}/original
é registrado exclusivamente por ligar_original(app), no main.py.

O GET /documentos/{id} continua sendo registrado pelo main.py.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api import rotas_status_fila as rotas
from app.api.rotas_decisao import (
    get_colaboradores,
    router_decisao,
    router_trilha,
)
from app.eventos import servico_padrao
from app.indice_revisao import IndiceRevisao
from app.revisao import Colaboradores


def ligar_fila_revisao(
    app: FastAPI,
    indice: IndiceRevisao | None = None,
) -> None:
    """Registra a fila de revisão e a trilha de auditoria."""

    indice = indice or IndiceRevisao(servico_padrao())

    app.include_router(rotas.router_fila)

    app.dependency_overrides[rotas.get_indice_revisao] = lambda: indice

    app.include_router(router_trilha)


def ligar_decisao(
    app: FastAPI,
    colaboradores: Colaboradores,
) -> None:
    """Registra a decisão da auditora."""

    app.include_router(router_decisao)

    app.dependency_overrides[get_colaboradores] = lambda: colaboradores
