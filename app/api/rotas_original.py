"""H4.3.1 T2 — GET /documentos/{documento_id}/original: devolve o original sem alterá-lo.

Registrada por ligar_fila_revisao (se a rota ainda não existir, por exemplo de H3.4.1).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app import storage

router_original = APIRouter()
ID_LIMPO = re.compile(r"^[A-Za-z0-9_-]+$")
TIPOS = {
    ".txt": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@router_original.get("/documentos/{documento_id}/original")
def original(documento_id: str):
    if not ID_LIMPO.fullmatch(documento_id or ""):
        return JSONResponse(
            status_code=400, content={"detail": "documento_id inválido"}
        )
    for extensao in storage.EXTENSOES:
        bruto = storage.ler(f"recebidos/{documento_id}{extensao}")
        if bruto is None:
            continue
        if isinstance(bruto, str):
            bruto = bruto.encode("utf-8")
        return Response(
            content=bruto,
            media_type=TIPOS.get(extensao, "application/octet-stream"),
            headers={
                "Content-Disposition": "inline",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )
    return JSONResponse(status_code=404, content={"detail": "documento não encontrado"})
