"""Modelos de classificação de documento (T1 — US "ver o tipo do documento").

O enum TipoDocumento é a FONTE ÚNICA das categorias do edital (as 6
categorias clínicas + "Desconhecido" como válvula de segurança). O Literal que
vai no response_schema do Gemini é GERADO a partir do enum, então os dois nunca
divergem.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class TipoDocumento(str, Enum):
    """As 6 categorias clínicas do edital + 'Desconhecido' (dúvida → revisão humana)."""

    RECEITUARIO_MEDICO = "Receituário Médico"
    LAUDO_IMAGEM = "Laudo de Exame de Imagem"
    LAUDO_LABORATORIAL = "Laudo Laboratorial"
    GUIA_PROCEDIMENTO = "Guia de Solicitação de Procedimento"
    RELATORIO_ALTA = "Relatório de Alta"
    ATESTADO_MEDICO = "Atestado Médico"
    DESCONHECIDO = "Desconhecido"

    def __str__(self) -> str:
        # f-string e comparação com str mostram o valor legível, não "Tipo.X"
        return self.value


# Literal gerado do enum — é o que vai no response_schema do Gemini (fallback
# decidido: enum Python no schema exige validação real com GEMINI_API_KEY,
# que não temos; ver bloco "Não testado sem chave" do PR).
TipoDocumentoLiteral = Literal[tuple(m.value for m in TipoDocumento)]

Prioridade = Literal["Urgente", "Prioritário", "Rotina"]


class Classificacao(BaseModel):
    """Os 4 campos de classificação mostrados ao analista (T1)."""

    tipo_documento: TipoDocumento
    especialidade: str | None = None
    nivel_prioridade: Prioridade
    score_confianca_classificacao: float = Field(ge=0, le=1)
