from datetime import date
from typing import Annotated

from fastapi import FastAPI, Query, Response
from fastapi.responses import JSONResponse

from app import historico
from app.modelos.classificacao import Prioridade, TipoDocumento
from app.modelos.destino import Destino
from app.status import StatusDocumento


def ligar_historico(app: FastAPI) -> None:
    """H5.2.1: GET /historico (filtros). H5.3.2: GET /historico/exportar?inicio=&fim="""

    @app.get(
        "/historico",
        responses={422: {"description": "Filtro inválido (data, tipo, prioridade...)"}},
    )
    def consultar_historico(
        data_inicio: Annotated[date | None, Query()] = None,
        data_fim: Annotated[date | None, Query()] = None,
        tipo: Annotated[list[TipoDocumento] | None, Query()] = None,
        prioridade: Annotated[list[Prioridade] | None, Query()] = None,
        destino: Annotated[list[Destino] | None, Query()] = None,
        status: Annotated[list[StatusDocumento] | None, Query()] = None,
    ):
        """Todos os filtros são opcionais e combináveis; repita o parâmetro para
        aceitar mais de um valor (ex.: ?tipo=A&tipo=B). Sem resultado: lista vazia."""
        try:
            return historico.consultar(
                data_inicio,
                data_fim,
                tipos=[t.value for t in tipo or []],
                prioridades=list(prioridade or []),
                destinos=[d.value for d in destino or []],
                status=[s.value for s in status or []],
            )
        except historico.ExportacaoInvalida as e:
            return JSONResponse(status_code=422, content={"detail": str(e)})

    @app.get(
        "/historico/exportar",
        responses={
            200: {"description": "Lista de ResultadoTriagem (JSON) do período"},
            422: {"description": "Período inválido ou registro fora do formato"},
        },
    )
    def exportar_historico(
        inicio: Annotated[date, Query()],
        fim: Annotated[date, Query()],
    ):
        try:
            resultados = historico.exportar(inicio, fim)
        except historico.ExportacaoInvalida as e:
            return JSONResponse(
                status_code=422,
                content={"detail": str(e)},
            )

        return Response(
            content=historico.serializar(resultados),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="mediflow_historico_{inicio}_{fim}.json"'
                )
            },
        )
