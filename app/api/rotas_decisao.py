"""H4.4.1 T3 — POST /documentos/{id}/decisao e GET /documentos/{id}/trilha (H5.3.1 T4).

O nome da auditora vem no corpo da requisição: não há autenticação, então a trilha
registra o que foi informado, não uma identidade comprovada.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.decisao import DecisaoAuditora
from app.eventos import servico_padrao
from app.revisao import (
    Colaboradores,
    DecisaoConflito,
    DecisaoInvalida,
    NaoEncontrado,
    decidir_caso,
)

router_decisao = APIRouter()
router_trilha = APIRouter()
ID_LIMPO = re.compile(r"^[A-Za-z0-9_-]+$")


def get_colaboradores() -> Colaboradores:
    raise NotImplementedError("ligar com ligar_decisao(app, colaboradores)")


ColabDep = Annotated[Colaboradores, Depends(get_colaboradores)]


@router_decisao.post("/documentos/{documento_id}/decisao")
def decidir(documento_id: str, decisao: DecisaoAuditora, colab: ColabDep):
    if not ID_LIMPO.fullmatch(documento_id or ""):
        return JSONResponse(
            status_code=400, content={"detail": "documento_id inválido"}
        )
    try:
        return decidir_caso(documento_id, decisao, colab)
    except NaoEncontrado as e:
        return JSONResponse(status_code=404, content={"detail": str(e)})
    except DecisaoConflito as e:
        return JSONResponse(status_code=409, content={"detail": str(e)})
    except DecisaoInvalida as e:
        return JSONResponse(status_code=422, content={"detail": str(e)})


@router_trilha.get("/documentos/{documento_id}/trilha")
def trilha(documento_id: str):
    if not ID_LIMPO.fullmatch(documento_id or ""):
        return JSONResponse(
            status_code=400, content={"detail": "documento_id inválido"}
        )
    eventos = servico_padrao().listar(documento_id)
    if not eventos:
        return JSONResponse(
            status_code=404, content={"detail": "documento não encontrado"}
        )
    problemas = servico_padrao().verificar_cadeia(documento_id)
    return {
        "documento_id": documento_id,
        "eventos": eventos,
        "cadeia_integra": not problemas,
        "problemas": problemas,
    }
