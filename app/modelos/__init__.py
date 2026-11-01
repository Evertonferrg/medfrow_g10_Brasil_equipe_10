# Fonte única dos modelos de classificação.
# O import quebrado de ".documento_entrada" foi removido: essa classe mora em
# app.schemas e nenhum código importa app.modelos.DocumentoEntrada.
from .classificacao import (
    Classificacao,
    Prioridade,
    TipoDocumento,
    TipoDocumentoLiteral,
)

__all__ = ["Classificacao", "Prioridade", "TipoDocumento", "TipoDocumentoLiteral"]
