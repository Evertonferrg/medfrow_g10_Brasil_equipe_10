from datetime import date
from typing import Annotated

from fastapi import FastAPI, Query, Response
from fastapi.responses import JSONResponse

from app import historico


def ligar_historico(app: FastAPI) -> None:
    """H5.3.2: GET /historico/exportar?inicio=AAAA-MM-DD&fim=AAAA-MM-DD"""

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
