import logging
import re
from pathlib import Path
from typing import Annotated

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import config, storage
from app.api.ligacao_documentos import ligar_documentos
from app.api.ligacao_fila import ligar_decisao, ligar_fila_revisao
from app.api.ligacao_historico import ligar_historico
from app.api.ligacao_original import ligar_original
from app.api.ligacao_regras import ligar_regras
from app.api.tempo import MedirTempoMiddleware, configurar_log
from app.arquivos import (
    MAPA_EXTENSAO_FORMATO,
    MAPA_FORMATO_EXTENSOES,
    extensao_aceita,
    extensao_por_assinatura,
    montar_mensagem_formato_invalido,
    montar_mensagem_tamanho_excedido,
)
from app.eventos import servico_padrao, status_do_documento
from app.indice_carga import lifespan_indice, registrar_chegada
from app.resposta import carregar_resultado
from app.revisao import colaboradores_padrao
from app.schemas import DocumentoEntrada, ResultadoTriagem, validar_id
from app.servico import processar
from app.status import StatusDocumento
from app.storage import FalhaArmazenamentoError, ObjetoJaExisteError

logger = logging.getLogger(__name__)

MAX_PDF = 10 * 1024 * 1024
MAX_ARQUIVO = 10 * 1024 * 1024

RESPOSTA_RESULTADO = {
    "model": ResultadoTriagem,
    "description": "Resultado da triagem",
}

RESPOSTAS_ERRO_ARQUIVO = {
    413: {"description": "Arquivo acima do limite permitido em MB"},
    415: {"description": "Formato de arquivo não aceito"},
}

MENSAGEM_FALHA_ORIGINAL = "Não foi possível guardar o documento. Tente novamente."

ID_LIMPO = re.compile(r"^[A-Za-z0-9_-]+$")


def _validar_id_limpo(documento_id: str):
    """Devolve None se o ID é limpo, ou 400 com o motivo."""
    if not ID_LIMPO.fullmatch(documento_id or ""):
        return JSONResponse(
            status_code=400,
            content={
                "detail": (
                    "documento_id inválido: use apenas letras, números, "
                    "'-' e '_', sem '/', '\\', '..' ou espaços."
                )
            },
        )
    return None


def _recebido(documento_id: str) -> bool:
    """True se o original já está em recebidos/."""
    return any(
        storage.existe(f"recebidos/{documento_id}{e}") for e in storage.EXTENSOES
    )


def _responder_consulta(documento_id: str):
    """Resultado validado, 202 se ainda processa, 404 se não existe."""
    try:
        resultado = carregar_resultado(documento_id)

    except ValidationError:
        logger.exception(
            "Resultado salvo fora do formato: %s",
            documento_id,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "resultado armazenado fora do formato combinado"},
        )

    if resultado is not None:
        resultado["status_documento"] = status_do_documento(
            documento_id,
            resultado,
        )
        return JSONResponse(
            status_code=200,
            content=resultado,
        )

    if _recebido(documento_id):
        return JSONResponse(
            status_code=202,
            content={
                "documento_id": documento_id,
                "status": "processando",
            },
        )

    return JSONResponse(
        status_code=404,
        content={"detail": "documento não encontrado"},
    )


def criar_app(extrator=None) -> FastAPI:

    if extrator is None:
        from app.llm import extrair as extrator

    app = FastAPI(
        title="MediFlow",
        version="0.1",
        lifespan=lifespan_indice,
    )

    configurar_log()

    app.add_middleware(MedirTempoMiddleware)

    @app.exception_handler(RequestValidationError)
    async def _422(request: Request, exc: RequestValidationError):
        erro = exc.errors()[0]

        campo = ".".join(str(p) for p in erro["loc"] if p != "body")

        msg = erro["msg"].replace("Value error, ", "")

        if erro["type"] == "missing":
            msg = f"campo obrigatório ausente: {campo}"

        return JSONResponse(
            status_code=422,
            content={"detail": msg},
        )

    def _aceitar(
        documento_id: str,
        conteudo: bytes,
        extensao: str,
        canal_origem: str | None = None,
    ) -> tuple[str | None, JSONResponse | None]:
        """
        Grava o original antes de qualquer processamento.
        A gravação é condicional para impedir substituição do original.
        """
        try:
            salvo = storage.salvar_original(
                documento_id,
                conteudo,
                extensao,
            )
        except ObjetoJaExisteError:
            return None, JSONResponse(
                status_code=409,
                content={"detail": f"documento_id já recebido: {documento_id}"},
            )
        except FalhaArmazenamentoError:
            logger.exception(
                "Falha ao guardar o original do documento %s", documento_id
            )
            try:
                servico_padrao().registrar_falha_armazenamento(
                    documento_id,
                    "Falha de armazenamento do original após três tentativas.",
                )
            except (OSError, ValueError):
                logger.exception("Não foi possível registrar a falha de armazenamento")

            return None, JSONResponse(
                status_code=503,
                content={"detail": MENSAGEM_FALHA_ORIGINAL},
            )

        try:
            servico_padrao().registrar(
                documento_id,
                StatusDocumento.RECEBIDO,
                canal_origem=canal_origem,
            )

        except (OSError, ValueError):
            logger.exception("Não foi possível registrar o evento de status")

        registrar_chegada(
            documento_id,
            canal_origem,
        )  # H2.4.1: entra na lista "Meus envios"

        return salvo["caminho_objeto"], None

    def _processar_original(
        documento_id: str,
        caminho: str,
        background: BackgroundTasks,
        aguardar: bool,
    ):
        """O grafo recebe o caminho do original já gravado."""

        if aguardar:
            return JSONResponse(
                status_code=200,
                content=processar(
                    documento_id,
                    "",
                    None,
                    extrator,
                    caminho_original=caminho,
                ),
            )

        background.add_task(
            processar,
            documento_id,
            "",
            None,
            extrator,
            caminho_original=caminho,
        )

        return {
            "documento_id": documento_id,
            "status": "recebido",
        }

    @app.post(
        "/triagem",
        status_code=202,
        responses={200: RESPOSTA_RESULTADO},
    )
    def enviar_texto(
        doc: DocumentoEntrada,
        background: BackgroundTasks,
        aguardar: bool = False,
    ):
        caminho, recusa = _aceitar(
            doc.documento_id,
            doc.documento_texto.encode("utf-8"),
            ".txt",
            getattr(doc, "canal_origem", None),
        )

        if recusa or caminho is None:
            return recusa

        return _processar_original(
            doc.documento_id,
            caminho,
            background,
            aguardar,
        )

    @app.post(
        "/triagem/pdf",
        status_code=202,
        responses={200: RESPOSTA_RESULTADO},
    )
    async def enviar_pdf(
        background: BackgroundTasks,
        documento_id: Annotated[str, Form()],
        canal_origem: Annotated[str, Form()],
        arquivo: Annotated[UploadFile, File()],
        aguardar: bool = False,
    ):
        try:
            documento_id = validar_id(documento_id)

        except ValueError as e:
            return JSONResponse(
                status_code=422,
                content={"detail": str(e)},
            )

        conteudo = await arquivo.read()

        if not conteudo.startswith(b"%PDF"):
            return JSONResponse(
                status_code=422,
                content={"detail": "o arquivo enviado não é um PDF"},
            )

        if len(conteudo) > MAX_PDF:
            return JSONResponse(
                status_code=413,
                content={"detail": "PDF acima de 10 MB"},
            )

        caminho, recusa = _aceitar(
            documento_id,
            conteudo,
            ".pdf",
            canal_origem,
        )

        if recusa or caminho is None:
            return recusa

        return _processar_original(
            documento_id,
            caminho,
            background,
            aguardar,
        )

    @app.post(
        "/triagem/arquivo",
        status_code=202,
        responses={
            200: RESPOSTA_RESULTADO,
            **RESPOSTAS_ERRO_ARQUIVO,
        },
    )
    async def enviar_arquivo(
        background: BackgroundTasks,
        documento_id: Annotated[str, Form()],
        canal_origem: Annotated[str, Form()],
        arquivo: Annotated[UploadFile, File()],
        aguardar: bool = False,
    ):
        """Valida formato e tamanho antes de persistir o arquivo."""

        try:
            documento_id = validar_id(documento_id)

        except ValueError as e:
            return JSONResponse(
                status_code=422,
                content={"detail": str(e)},
            )

        limite_mb = config.tamanho_maximo_mb()
        max_bytes = limite_mb * 1024 * 1024

        formatos = config.formatos_aceitos()

        msg_formato = montar_mensagem_formato_invalido(formatos)
        msg_tamanho = montar_mensagem_tamanho_excedido(limite_mb)

        if arquivo.filename:
            ext_nome = Path(arquivo.filename).suffix.lower()

            if ext_nome and not extensao_aceita(
                arquivo.filename,
                formatos,
            ):
                return JSONResponse(
                    status_code=415,
                    content={"detail": msg_formato},
                )

        conteudo = await arquivo.read(max_bytes + 1)

        if len(conteudo) > max_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": msg_tamanho},
            )

        extensao = extensao_por_assinatura(conteudo)

        if extensao is None:
            return JSONResponse(
                status_code=415,
                content={"detail": msg_formato},
            )

        formato_detectado = MAPA_EXTENSAO_FORMATO.get(extensao)

        if formato_detectado not in formatos:
            return JSONResponse(
                status_code=415,
                content={"detail": msg_formato},
            )

        if arquivo.filename:
            ext_nome = Path(arquivo.filename).suffix.lower()

            if ext_nome and ext_nome not in MAPA_FORMATO_EXTENSOES.get(
                formato_detectado,
                set(),
            ):
                return JSONResponse(
                    status_code=415,
                    content={"detail": msg_formato},
                )

        caminho, recusa = _aceitar(
            documento_id,
            conteudo,
            extensao,
            canal_origem,
        )

        if recusa or caminho is None:
            return recusa

        return _processar_original(
            documento_id,
            caminho,
            background,
            aguardar,
        )

    @app.get(
        "/triagem/{documento_id}",
        responses={200: RESPOSTA_RESULTADO},
    )
    def consultar(documento_id: str):
        try:
            validar_id(documento_id)

        except ValueError as e:
            return JSONResponse(
                status_code=422,
                content={"detail": str(e)},
            )

        return _responder_consulta(documento_id)

    @app.get(
        "/documentos/{documento_id}",
        responses={200: RESPOSTA_RESULTADO},
    )
    def consultar_documento(documento_id: str):
        """Mesmo formato de resposta de GET /triagem/{id}."""

        recusa = _validar_id_limpo(documento_id)

        if recusa:
            return recusa

        return _responder_consulta(documento_id)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Registro das rotas
    # H3.4.1: registra primeiro a rota do documento original.
    ligar_original(app)

    # H4.2.1: GET /filas/revisao
    ligar_fila_revisao(app)

    # H4.4.1: POST /documentos/{id}/decisao
    ligar_decisao(app, colaboradores_padrao())

    # H5.3.2: GET /historico/exportar
    ligar_historico(app)

    # H2.4.1: GET /documentos
    ligar_documentos(app)

    # H6.1.1: PUT /regras/limite e GET /regras
    ligar_regras(app)

    return app


try:
    app = criar_app()

except Exception:
    logger.exception("Falha ao criar a aplicação")
    app = None
