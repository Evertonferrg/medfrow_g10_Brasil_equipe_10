"""H2.3.2 T4 (GET /documentos/{id}), H4.2.1 T1 e H4.2.2 T1 (GET /filas/revisao).

Ligue no main.py:
    app.include_router(rotas_status_fila.router)
    app.dependency_overrides[get_eventos] = lambda: servico_eventos
    app.dependency_overrides[get_indice_revisao] = lambda: indice_em_memoria
    app.dependency_overrides[get_resultados] = lambda: armazenamento
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.eventos import ServicoEventos
from app.fila import ordenar_fila

router = APIRouter()


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


@router.get("/filas/revisao")
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
