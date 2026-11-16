"""H3.4.1 T1 — GET /documentos/{documento_id}/original.

O router recebe duas funções, para você ligar ao que já existe no projeto
(e para os testes usarem dublês, sem OCI):

  buscar_documento(documento_id) -> dict | None
      precisa trazer "chave" (objeto em recebidos/) e, se tiver,
      "content_type" e "nome_arquivo".
  ler_objeto(chave) -> bytes
      devolve os bytes do bucket; levanta FileNotFoundError se não existir.

A chave vem sempre do registro do documento, nunca do parâmetro da URL,
para não permitir ler objetos arbitrários do bucket.
"""

import io
import mimetypes
from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse


def criar_router_original(
    buscar_documento: Callable[[str], dict | None],
    ler_objeto: Callable[[str], bytes],
) -> APIRouter:
    router = APIRouter()

    @router.get("/documentos/{documento_id}/original")
    def original(documento_id: str):
        documento = buscar_documento(documento_id)
        if not documento:
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        try:
            conteudo = ler_objeto(documento["chave"])
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail="Arquivo original não encontrado"
            )

        nome = documento.get("nome_arquivo") or documento["chave"].rsplit("/", 1)[-1]
        tipo = (
            documento.get("content_type")
            or mimetypes.guess_type(nome)[0]
            or "application/octet-stream"
        )
        nome_ascii = nome.encode("ascii", "ignore").decode() or "documento"
        return StreamingResponse(
            io.BytesIO(conteudo),
            media_type=tipo,
            headers={
                "Content-Length": str(len(conteudo)),
                "Content-Disposition": f'inline; filename="{nome_ascii}"',
            },
        )

    return router


# Em app/main.py (ajuste os nomes aos do seu projeto):
#   from app.api.original import criar_router_original
#   app.include_router(criar_router_original(repo.buscar_documento, storage.ler))
