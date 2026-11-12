import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from app import storage
from app.eventos import servico_padrao, status_do_documento
from app.indice_documentos import ResumoDocumento, indice, resumo_de_resultado
from app.status import StatusDocumento

logger = logging.getLogger(__name__)

_EPOCA = datetime(
    1970, 1, 1, tzinfo=UTC
)  # sem evento de chegada: vai para o fim da lista


def _chegada(documento_id) -> datetime | None:
    """Hora do 1º evento (recebido) do documento, sempre com fuso (UTC se vier sem)."""
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


def _status(documento_id: str, resultado: dict) -> str | None:
    try:
        return status_do_documento(documento_id, resultado)
    except Exception:
        logger.exception("Índice: não consegui calcular o status de %s", documento_id)
        return None


def reconstruir_do_bucket() -> int:
    """Lê os resultados já gravados uma vez e monta o índice. Devolve quantos entraram."""
    from app.historico import PREFIXOS  # import tardio: evita ciclo na inicialização

    resumos: list[ResumoDocumento] = []
    for prefixo in PREFIXOS:
        for caminho in storage.listar(prefixo):
            if not caminho.endswith(".json"):
                continue
            try:
                dados = json.loads(storage.ler(caminho))
                doc_id = dados["documento_id"]
                resumos.append(
                    resumo_de_resultado(
                        dados,
                        status=_status(doc_id, dados),
                        data=_chegada(doc_id) or _EPOCA,
                    )
                )
            except (TypeError, ValueError, KeyError):
                logger.warning(
                    "Índice: %s ignorado (JSON ausente ou fora do formato)", caminho
                )
    indice.reconstruir(resumos)
    return len(resumos)


def registrar_chegada(documento_id: str, canal_origem: str | None) -> None:
    """Documento recebido, ainda sem resultado: entra na lista como 'Recebido'."""
    try:
        recebido = getattr(StatusDocumento.RECEBIDO, "value", StatusDocumento.RECEBIDO)
        indice.atualizar(
            ResumoDocumento(
                documento_id=documento_id,
                status=str(recebido),
                data=datetime.now(UTC),
                canal_origem=canal_origem,
            )
        )
    except Exception:
        logger.exception("Índice: falha ao registrar a chegada de %s", documento_id)


def registrar_resultado(documento_id: str, resultado: dict) -> None:
    """Resultado gravado: atualiza o resumo, mantendo o canal e a data da chegada."""
    try:
        existente = indice.obter(documento_id)
        indice.atualizar(
            resumo_de_resultado(
                resultado,
                canal_origem=existente.canal_origem if existente else None,
                status=_status(documento_id, resultado),
                data=existente.data
                if existente
                else (_chegada(documento_id) or _EPOCA),
            )
        )
    except Exception:
        logger.exception("Índice: falha ao registrar o resultado de %s", documento_id)


@asynccontextmanager
async def lifespan_indice(app):
    """Na subida da API: reconstrói o índice. Falha aqui nunca impede a API de subir."""
    try:
        logger.info("Índice de documentos reconstruído: %d", reconstruir_do_bucket())
    except Exception:
        logger.exception("Índice: reconstrução falhou; a lista começa vazia")
    yield
