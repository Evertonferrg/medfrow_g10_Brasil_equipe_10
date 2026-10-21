from typing import Optional
from .grafo import triar
from .resposta import arquivar

def processar(documento_id: str, texto: str, pdf_bytes: Optional[bytes], extrator) -> dict:
    """Roda o grafo e arquiva o resultado. """
    try:
        estado = triar(texto, extrator, pdf_bytes)
    except Exception as e: # se tiver falha vai para revisao humana
        estado = {"texto": texto, "extracao": None, "erro": f"Falha de processamento: {e}",
                  "problemas": [], "score": 0.0, "destino": "Fila_Revisao_Humana",
                  "regra": "R-REVISAO", "requer_revisao": True, "notificacao": None,
                  "justificativa": f"Enviado à revisão humana (regra R-REVISAO): falha de processamento ({str(e)[:80]})."}
    return arquivar(documento_id, estado)