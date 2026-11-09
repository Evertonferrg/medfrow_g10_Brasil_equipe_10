"""Liga a fila de revisão ao app. No main.py, dentro de criar_app, depois de criar `app`:

    from app.api.ligacao_fila import ligar_fila_revisao
    ligar_fila_revisao(app)

Registra só GET /filas/revisao. O GET /documentos/{id} continua sendo o do main.py.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api import rotas_status_fila as rotas
from app.api.rotas_original import router_original
from app.eventos import servico_padrao
from app.indice_revisao import IndiceRevisao

ROTA_ORIGINAL = "/documentos/{documento_id}/original"


def ligar_fila_revisao(app: FastAPI, indice: IndiceRevisao | None = None) -> None:
    indice = indice or IndiceRevisao(servico_padrao())
    app.include_router(rotas.router_fila)
    app.dependency_overrides[rotas.get_indice_revisao] = lambda: indice
    if not any(getattr(r, "path", None) == ROTA_ORIGINAL for r in app.routes):
        app.include_router(router_original)
