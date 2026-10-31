from typing import Optional

from . import storage
from .grafo import triar
from .resposta import arquivar


def _carregar_original(caminho: str) -> tuple[str, Optional[bytes]]:
    """H5.1.1 T3: o grafo parte do que está GRAVADO em recebidos/, não do upload em memória."""
    dados = storage.ler(caminho)
    if dados is None:
        raise FileNotFoundError(f"original não encontrado: {caminho}")
    if caminho.endswith(".txt"):
        return dados.decode("utf-8"), None
    return "", dados


def processar(documento_id: str, texto: str, pdf_bytes: Optional[bytes], extrator,
              caminho_original: Optional[str] = None) -> dict:
    """Roda o grafo e arquiva o resultado.

    Com caminho_original, o conteúdo é lido de recebidos/ (texto e pdf_bytes são ignorados).
    """
    try:
        if caminho_original:
            texto, pdf_bytes = _carregar_original(caminho_original)
        estado = triar(texto, extrator, pdf_bytes, documento_id=documento_id)
    except Exception as e:  # se tiver falha vai para revisao humana
        estado = {"texto": texto, "extracao": None, "erro": f"Falha de processamento: {e}",
                  "problemas": [], "score": 0.0, "destino": "Fila_Revisao_Humana",
                  "regra": "R-REVISAO", "requer_revisao": True, "notificacao": None,
                  "justificativa": f"Enviado à revisão humana (regra R-REVISAO): falha de processamento ({str(e)[:80]})."}
    return arquivar(documento_id, estado)
