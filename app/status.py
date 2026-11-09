"""H2.3.2 T1 — status do documento. H4.4.3 acrescentará REJEITADO."""

from enum import Enum


class StatusDocumento(str, Enum):
    RECEBIDO = "recebido"
    PROCESSANDO = "processando"
    PROCESSADO = "processado"
    EM_AUDITORIA_HUMANA = "em_auditoria_humana"
