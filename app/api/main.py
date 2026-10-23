import json
import logging

from fastapi import FastAPI, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import config, storage
from app.schemas import DocumentoEntrada, validar_id
from app.servico import processar
from app.storage import ObjetoJaExisteError
from app.api.tempo import MedirTempoMiddleware, configurar_log

logger = logging.getLogger(__name__)

PASTAS_RESULTADO = ('processados/urgentes', 'processados/rotina', 'auditoria_humana')
MAX_PDF = 10 * 1024 * 1024

def criar_app(extrator=None) -> FastAPI:
    if extrator is None:
        from app.llm import extrair as extrator
    app = FastAPI(title='MediFlow', version='0.1')
    configurar_log()
    app.add_middleware(MedirTempoMiddleware)   # T8: log da duração de cada requisição

    @app.exception_handler(RequestValidationError)
    async def _422(request: Request, exc: RequestValidationError):
        erro = exc.errors()[0]
        campo = ".".join(str(p) for p in erro['loc'] if p != "body" )
        msg = erro["msg"].replace("Value error, ", "")
        if erro["type"] == "missing":
            msg = f"campo obrigatório ausente: {campo}"
        return JSONResponse(status_code=422, content={"detail": msg})

    def _aceitar(documento_id: str, conteudo: bytes, extensao: str):
        """Recusa ID repetido (409) e grava o original ANTES de qualquer processamento.

        A gravação usa sobrescrever=False: é atômica, então dois envios simultâneos
        com o mesmo ID não passam os dois e o original nunca é trocado.
        """
        recusa = JSONResponse(status_code=409,
                              content={"detail": f"documento_id já recebido: {documento_id}"})
        outra = ".pdf" if extensao == ".txt" else ".txt"
        if storage.existe(f"recebidos/{documento_id}{outra}"):
            return recusa
        try:
            storage.salvar(f"recebidos/{documento_id}{extensao}", conteudo, sobrescrever=False)
        except ObjetoJaExisteError:
            return recusa
        return None

    @app.post("/triagem", status_code=202)
    def enviar_texto(doc: DocumentoEntrada, background: BackgroundTasks, aguardar: bool = False):
        recusa = _aceitar(doc.documento_id, doc.documento_texto.encode("utf-8"), ".txt")
        if recusa:
            return recusa
        if aguardar:
            return JSONResponse(status_code=200, content=processar(
                doc.documento_id, doc.documento_texto, None, extrator))

        background.add_task(processar, doc.documento_id, doc.documento_texto, None, extrator)
        return {"documento_id": doc.documento_id, "status": "recebido"}

    @app.post("/triagem/pdf", status_code=202)
    async def enviar_pdf(background: BackgroundTasks, documento_id: str = Form(...),
                         canal_origem: str = Form(...), arquivo: UploadFile = File(...),
                         aguardar: bool = False):
        try:
            documento_id = validar_id(documento_id)
        except ValueError as e:
            return JSONResponse(status_code=422, content={"detail": str(e)})
        conteudo = await arquivo.read()
        if not conteudo.startswith(b"%PDF"):
            return JSONResponse(status_code=422, content={"detail": "o arquivo enviado não é um PDF"})
        if len(conteudo) > MAX_PDF:
            return JSONResponse(status_code=413, content={"detail": "PDF acima de 10 MB"})
        recusa = _aceitar(documento_id, conteudo, ".pdf")
        if recusa:
            return recusa
        if aguardar:
            return JSONResponse(status_code=200, content=processar(documento_id, "", conteudo, extrator))
        background.add_task(processar, documento_id, "", conteudo, extrator)
        return {"documento_id": documento_id, "status": "recebido"}

    @app.get("/triagem/{documento_id}")
    def consultar(documento_id: str):
        try:
            validar_id(documento_id)
        except ValueError as e:
            return JSONResponse(status_code=422, content={"detail": str(e)})
        for pasta in PASTAS_RESULTADO:
            bruto = storage.ler(f"{pasta}/{documento_id}.json")
            if bruto is not None:
                resultado = json.loads(bruto)
                resultado["armazenamento_oci"] = {"bucket": config.bucket(),
                                                 "caminho_objeto": f"{pasta}/{documento_id}.json",
                                                 "urgente": pasta.endswith("urgentes")}
                return resultado
        if storage.existe(f"recebidos/{documento_id}.txt") or storage.existe(f"recebidos/{documento_id}.pdf"):
            return JSONResponse(status_code=202, content={"documento_id": documento_id, "status": "processando"})
        return JSONResponse(status_code=404, content={"detail": "documento não encontrado"})

    return app

try:
    app = criar_app()
except Exception:
    # Mostra o erro real no terminal em vez de subir uma aplicação vazia sem explicação.
    logger.exception("Falha ao criar a aplicação")
    app = None
