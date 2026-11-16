"""H3.4.1 T1 — liga GET /documentos/{documento_id}/original."""

import re

from fastapi import FastAPI

from app import storage
from app.api.original import criar_router_original

ID_LIMPO = re.compile(r"^[A-Za-z0-9_-]+$")


def _buscar_documento(documento_id: str) -> dict | None:
    """Acha o original em recebidos/ (qualquer extensão aceita)."""
    if not ID_LIMPO.fullmatch(documento_id or ""):
        return None  # ID fora do charset limpo vira 404, sem montar caminho
    for ext in storage.EXTENSOES:
        chave = f"recebidos/{documento_id}{ext}"
        if storage.existe(chave):
            return {"chave": chave, "nome_arquivo": f"{documento_id}{ext}"}
    return None


def _ler_objeto(chave: str) -> bytes:
    dados = storage.ler(chave)
    if dados is None:
        raise FileNotFoundError(chave)  # a rota converte em 404
    return dados


def ligar_original(app: FastAPI) -> None:
    app.include_router(criar_router_original(_buscar_documento, _ler_objeto))
