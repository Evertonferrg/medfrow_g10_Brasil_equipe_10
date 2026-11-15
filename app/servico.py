import logging
import os

from . import storage
from .grafo import triar
from .indice_carga import registrar_resultado  # H2.4.1
from .resposta import arquivar

# from .schemas import Extracao

logger = logging.getLogger(__name__)


def _carregar_original(caminho: str) -> tuple[str, bytes | None]:
    """H5.1.1 T3: o grafo parte do que está GRAVADO em recebidos/, não do upload em memória."""
    dados = storage.ler(caminho)
    if dados is None:
        raise FileNotFoundError(f"original não encontrado: {caminho}")

    if caminho.endswith(".txt"):
        return dados.decode("utf-8"), None

    return "", dados


def processar(
    documento_id: str,
    texto: str,
    pdf_bytes: bytes | None,
    extrator,
    caminho_original: str | None = None,
) -> dict:
    """Roda o grafo e arquiva o resultado.

    Com caminho_original, o conteúdo é lido de recebidos/
    (texto e pdf_bytes são ignorados).
    """
    try:
        if caminho_original:
            texto, pdf_bytes = _carregar_original(caminho_original)

        estado = triar(
            texto,
            extrator,
            pdf_bytes,
            documento_id=documento_id,
        )

    except Exception as e:  # se tiver falha vai para revisão humana
        logger.exception("Falha no processamento")

        estado = {
            "texto": texto,
            "extracao": None,
            "erro": f"Falha de processamento: {e}",
            "problemas": [],
            "score": 0.0,
            "destino": "Fila_Revisao_Humana",
            "regra": "R-REVISAO",
            "requer_revisao": True,
            "notificacao": None,
            "justificativa": (
                "Enviado à revisão humana (regra R-REVISAO): "
                f"falha de processamento ({str(e)[:80]})."
            ),
        }

    # Arquiva o resultado independentemente de o grafo ter sucesso ou falhar.
    resultado = arquivar(documento_id, estado)

    # Atualiza o índice "Meus envios".
    registrar_resultado(documento_id, resultado)

    # Notificações automáticas ficam desativadas por padrão.
    notificacao_automatica = os.getenv(
        "NOTIFICACAO_AUTOMATICA",
        "false",
    ).strip().lower() in ("1", "true", "yes", "sim", "on")

    if notificacao_automatica:
        try:
            decisao = resultado.get("decisao_roteamento") or {}
            destino = decisao.get("destino_principal")
            destino = getattr(destino, "value", destino)

            if destino == "Fila_Emergencia_Medica":
                from .notificacao import notificar_responsavel_por_destino

                status_notificacao = notificar_responsavel_por_destino(resultado)

                logger.info(
                    "Alerta de emergência do documento %s: %s",
                    documento_id,
                    status_notificacao,
                )

        except Exception:
            # Uma falha de notificação não desfaz o processamento.
            logger.exception(
                "Falha ao notificar plantão do documento %s",
                documento_id,
            )
    return resultado
