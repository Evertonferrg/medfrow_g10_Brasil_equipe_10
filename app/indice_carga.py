import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from app import storage
from app.eventos import servico_padrao, status_do_documento
from app.indice_documentos import ResumoDocumento, indice, resumo_de_resultado
from app.status import StatusDocumento

logger = logging.getLogger(__name__)
MAX_WORKERS_LEITURA = 8

_EPOCA = datetime(
    1970, 1, 1, tzinfo=UTC
)  # sem evento de chegada: vai para o fim da lista


def _chegada(documento_id: str) -> datetime | None:
    """Recupera a hora do primeiro evento do documento."""
    if not isinstance(documento_id, str):
        return None

    try:
        eventos = servico_padrao().listar(documento_id)

        if not eventos:
            return None

        quando = datetime.fromisoformat(eventos[0]["em"])

    except (OSError, ValueError, KeyError):
        return None

    return quando if quando.tzinfo else quando.replace(tzinfo=UTC)


def _canal_origem(documento_id: str) -> str | None:
    """Recupera o canal de origem registrado no primeiro evento."""
    try:
        eventos = servico_padrao().listar(documento_id)

        if not eventos:
            return None

        canal = eventos[0].get("canal_origem")

        if isinstance(canal, str) and canal.strip():
            return canal.strip()

    except (OSError, ValueError, KeyError):
        logger.exception(
            "Não foi possível recuperar a origem de %s",
            documento_id,
        )

    return None


def _status(documento_id: str, resultado: dict) -> str | None:
    """Recupera o status atual do documento."""
    try:
        return status_do_documento(documento_id, resultado)

    except Exception:
        logger.exception(
            "Índice: não consegui calcular o status de %s",
            documento_id,
        )
        return None


def _carregar_resumo(caminho: str) -> ResumoDocumento | None:
    try:
        bruto = storage.ler(caminho)
        if bruto is None:
            return None
        dados = json.loads(bruto)
        doc_id = dados["documento_id"]
        return resumo_de_resultado(
            dados,
            canal_origem=_canal_origem(doc_id),
            status=_status(doc_id, dados),
            data=_chegada(doc_id) or _EPOCA,
        )
    except (TypeError, ValueError, KeyError):
        logger.warning(
            "Índice: %s ignorado (JSON ausente ou fora do formato)",
            caminho,
        )
        return None


def reconstruir_do_bucket() -> int:
    """Reconstrói o índice usando os resultados e eventos já gravados."""
    from app.historico import PREFIXOS

    caminhos: list[str] = []
    for prefixo in PREFIXOS:
        for caminho in storage.listar(prefixo):
            if not caminho.endswith(".json") or caminho.endswith(".estado.json"):
                continue
            caminhos.append(caminho)

    if len(caminhos) <= 1:
        carregados = [_carregar_resumo(c) for c in caminhos]
    else:
        workers = min(MAX_WORKERS_LEITURA, len(caminhos))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            carregados = list(executor.map(_carregar_resumo, caminhos))

    resumos = [r for r in carregados if r is not None]
    indice.reconstruir(resumos)

    return len(resumos)


def registrar_chegada(
    documento_id: str,
    canal_origem: str | None,
) -> None:
    """Registra a chegada do documento no índice."""
    try:
        recebido = getattr(
            StatusDocumento.RECEBIDO,
            "value",
            StatusDocumento.RECEBIDO,
        )

        indice.atualizar(
            ResumoDocumento(
                documento_id=documento_id,
                status=str(recebido),
                data=datetime.now(UTC),
                canal_origem=canal_origem,
            )
        )

    except Exception:
        logger.exception(
            "Índice: falha ao registrar a chegada de %s",
            documento_id,
        )


def registrar_resultado(
    documento_id: str,
    resultado: dict,
) -> None:
    """Atualiza o resumo preservando o canal e a data da chegada."""
    try:
        existente = indice.obter(documento_id)

        indice.atualizar(
            resumo_de_resultado(
                resultado,
                canal_origem=(
                    existente.canal_origem if existente else _canal_origem(documento_id)
                ),
                status=_status(documento_id, resultado),
                data=(
                    existente.data if existente else (_chegada(documento_id) or _EPOCA)
                ),
            )
        )

    except Exception:
        logger.exception(
            "Índice: falha ao registrar o resultado de %s",
            documento_id,
        )


@asynccontextmanager
async def lifespan_indice(app):
    """Reconstrói o índice quando a API inicia."""
    try:
        total = reconstruir_do_bucket()

        logger.info(
            "Índice de documentos reconstruído: %d",
            total,
        )

    except Exception:
        logger.exception("Índice: reconstrução falhou; a lista começa vazia")

    yield
