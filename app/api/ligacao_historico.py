from datetime import date
from typing import Annotated

from fastapi import FastAPI, Query, Response
from fastapi.responses import JSONResponse

from app import historico
from app.eventos import servico_padrao
from app.modelos.evento import Evento
from app.schemas import validar_id


def ligar_historico(app: FastAPI) -> None:
    """Rotas de histórico de documentos e exportação (H5.2.2 / H5.3.2)."""

    @app.get(
        "/documentos/{documento_id}/historico",
        response_model=list[Evento],
        responses={
            200: {"description": "Lista de eventos em ordem cronológica"},
            404: {"description": "Documento não encontrado ou sem histórico"},
            422: {"description": "ID de documento inválido"},
        },
    )
    def obter_historico_documento(documento_id: str):
        """H5.2.2 T3: Devolve a linha do tempo / eventos em ordem cronológica."""
        try:
            validar_id(documento_id)
        except ValueError as e:
            return JSONResponse(status_code=422, content={"detail": str(e)})

        eventos = servico_padrao().listar_eventos(documento_id)
        if not eventos:
            # Também verifica se existem eventos brutos registrados
            brutos = servico_padrao().listar(documento_id)
            if not brutos:
                return JSONResponse(
                    status_code=404,
                    content={"detail": f"Histórico não encontrado para documento {documento_id}"},
                )
        return [e.model_dump() for e in eventos]

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
        """H5.3.2: GET /historico/exportar?inicio=AAAA-MM-DD&fim=AAAA-MM-DD"""
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
