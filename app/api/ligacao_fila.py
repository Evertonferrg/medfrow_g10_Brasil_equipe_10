"""Liga a fila de revisão, o original e a trilha ao app. No main.py, dentro de criar_app:

    from app.api.ligacao_fila import ligar_fila_revisao
    ligar_fila_revisao(app)

A decisão da auditora (POST /documentos/{id}/decisao) só é registrada quando houver
colaboradores reais: ligar_decisao(app, Colaboradores(...)).
O GET /documentos/{id} continua sendo o do main.py.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api import rotas_status_fila as rotas
from app.api.rotas_decisao import get_colaboradores, router_decisao, router_trilha
from app.api.rotas_original import router_original
from app.eventos import servico_padrao
from app.indice_revisao import IndiceRevisao
from app.revisao import Colaboradores

ROTA_ORIGINAL = "/documentos/{documento_id}/original"


def ligar_fila_revisao(app: FastAPI, indice: IndiceRevisao | None = None) -> None:
    indice = indice or IndiceRevisao(servico_padrao())
    app.include_router(rotas.router_fila)
    app.dependency_overrides[rotas.get_indice_revisao] = lambda: indice
    if not any(getattr(r, "path", None) == ROTA_ORIGINAL for r in app.routes):
        app.include_router(router_original)
    app.include_router(router_trilha)


def ligar_decisao(app: FastAPI, colaboradores: Colaboradores) -> None:
    app.include_router(router_decisao)
    app.dependency_overrides[get_colaboradores] = lambda: colaboradores
