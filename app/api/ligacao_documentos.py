from typing import Annotated

from fastapi import FastAPI, Query

from app.indice_documentos import IndiceDocumentos, ResumoDocumento
from app.indice_documentos import indice as indice_padrao


def ligar_documentos(app: FastAPI, indice: IndiceDocumentos = indice_padrao) -> None:
    """H2.4.1: GET /documentos?canal_origem=... (mais recente primeiro)."""

    @app.get(
        "/documentos",
        response_model=list[ResumoDocumento],
        responses={200: {"description": "Resumo dos documentos enviados, do mais recente ao mais antigo"}},
    )
    def listar_documentos(canal_origem: Annotated[str | None, Query()] = None):
        return indice.listar(canal_origem)