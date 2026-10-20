from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.servicos.armazenamento import DocumentoJaExisteError

MENSAGENS = {
    "missing": "campo obrigatório",
    "string_type": "deve ser um texto",
    "json_invalid": "JSON inválido",
}


def _traduzir(erro: dict) -> dict:
    tipo = erro["type"]
    if tipo == "value_error":
        mensagem = erro["msg"].removeprefix("Value error, ")
    else:
        mensagem = MENSAGENS.get(tipo, "valor inválido")

    if tipo == "json_invalid":
        campo = "corpo"
    else:
        campo = ".".join(str(p) for p in erro["loc"] if p != "body") or "corpo"
    return {"campo": campo, "mensagem": mensagem}


async def tratar_validacao(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "erro": "Requisição inválida",
            "detalhes": [_traduzir(e) for e in exc.errors()],
        },
    )


async def tratar_duplicado(request: Request, exc: DocumentoJaExisteError):
    return JSONResponse(
        status_code=409,
        content={"erro": f"documento_id '{exc.documento_id}' já existe em recebidos"},
    )


def registrar_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, tratar_validacao)
    app.add_exception_handler(DocumentoJaExisteError, tratar_duplicado)
