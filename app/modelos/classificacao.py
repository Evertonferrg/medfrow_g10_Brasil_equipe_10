from enum import Enum
from typing import Literal, Optional

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
        return self.value


TipoDocumentoLiteral = Literal[tuple(m.value for m in TipoDocumento)]

Prioridade = Literal["Urgente", "Rotina"]


class Destino(str, Enum):
    """Destinos finais do roteamento clínico."""

    FARMACIA_HOSPITALAR = "Farmacia_Hospitalar"
    AUDITORIA_AUTORIZACOES = "Auditoria_Autorizacoes"
    PRONTUARIO_ELETRONICO = "Prontuario_Eletronico"
    FILA_EMERGENCIA_MEDICA = "Fila_Emergencia_Medica"
    FILA_REVISAO_HUMANA = "Fila_Revisao_Humana"

    def __str__(self) -> str:
        return self.value


class Classificacao(BaseModel):
    """Os 4 campos de classificação mostrados ao analista (T1)."""

    tipo_documento: TipoDocumento
    especialidade: Optional[str] = None
    nivel_prioridade: Prioridade
    score_confianca_classificacao: float = Field(ge=0, le=1)
