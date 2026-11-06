"""H2.3.2 T4 (GET /documentos/{id}), H4.2.1 T1 e H4.2.2 T1 (GET /filas/revisao).

A fila é ligada por app.api.ligacao_fila.ligar_fila_revisao(app).
O `router` de /documentos/{id} não está registrado: o main.py já tem essa rota (H2.3.1).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.eventos import ServicoEventos
from app.fila import ordenar_fila

router = (
    APIRouter()
)  # GET /documentos/{id} com status (H2.3.2): ainda não registrado no app
router_fila = APIRouter()  # GET /filas/revisao


def get_eventos() -> ServicoEventos:
    raise NotImplementedError("ligar no main.py")


def get_indice_revisao():
    """Objeto com .listar_casos_revisao() -> list[CasoRevisao]."""
    raise NotImplementedError("ligar no main.py")


def get_resultados():
    """Objeto com .obter(documento_id) -> dict | None."""
    raise NotImplementedError("ligar no main.py")


EventosDep = Annotated[ServicoEventos, Depends(get_eventos)]
IndiceDep = Annotated[object, Depends(get_indice_revisao)]
ResultadosDep = Annotated[object, Depends(get_resultados)]


@router.get("/documentos/{documento_id}")
def consultar_documento(
    documento_id: str, eventos: EventosDep, resultados: ResultadosDep
):
    try:
        status = eventos.status_atual(documento_id)
    except ValueError:  # id fora do padrão: trata como inexistente
        status = None
    if status is None:
        raise HTTPException(status_code=404, detail="documento não encontrado")
    return {
        "documento_id": documento_id,
        "status": status.value,
        "resultado": resultados.obter(documento_id),
    }


@router_fila.get("/filas/revisao")
def fila_revisao(indice: IndiceDep):
    casos = ordenar_fila(indice.listar_casos_revisao())
    return [
        {
            "documento_id": c.documento_id,
            "tipo": c.tipo,
            "motivos": c.motivos,
            "chegada_em": c.chegada_em.isoformat(),
            "prioridade": getattr(c.prioridade, "value", c.prioridade),
            "destaques_dose": c.destaques_dose,
        }
        for c in casos
    ]
