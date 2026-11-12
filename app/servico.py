import logging

from . import storage
from .grafo import triar
from .resposta import arquivar
from .indice_carga import registrar_resultado  # H2.4.1
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
    extrator,  # Extracao,
    caminho_original: str | None = None,
) -> dict:
    """Roda o grafo e arquiva o resultado.

    Com caminho_original, o conteúdo é lido de recebidos/ (texto e pdf_bytes são ignorados).
    """
    try:
        if caminho_original:
            texto, pdf_bytes = _carregar_original(caminho_original)
        estado = triar(texto, extrator, pdf_bytes, documento_id=documento_id)
    except Exception as e:  # se tiver falha vai para revisao humana
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
            "justificativa": f"Enviado à revisão humana (regra R-REVISAO): falha de processamento ({str(e)[:80]}).",
        }
    resultado = arquivar(documento_id, estado)
    registrar_resultado(documento_id, resultado)  # H2.4.1: atualiza o índice "Meus envios"
    return resultado
