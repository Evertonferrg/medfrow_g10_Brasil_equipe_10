"""Enum Destino e modelos de roteamento (H2.1.1 T1).

O enum Destino é a FONTE ÚNICA dos destinos de roteamento previstos
no edital e em config/regras.json.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class Destino(str, Enum):
    """Destinos de roteamento previstos pelo edital e regras de negócio."""

    FARMACIA_HOSPITALAR = "Farmacia_Hospitalar"
    AUDITORIA_AUTORIZACOES = "Auditoria_Autorizacoes"
    PRONTUARIO_ELETRONICO = "Prontuario_Eletronico"
    FILA_EMERGENCIA_MEDICA = "Fila_Emergencia_Medica"
    FILA_REVISAO_HUMANA = "Fila_Revisao_Humana"

    def __str__(self) -> str:
        return self.value


DestinoLiteral = Literal[
    "Farmacia_Hospitalar",
    "Auditoria_Autorizacoes",
    "Prontuario_Eletronico",
    "Fila_Emergencia_Medica",
    "Fila_Revisao_Humana",
]


class Notificacao(BaseModel):
    """Notificação gerada pelo roteamento (ex.: alerta plantão médico)."""

    canal: str
    mensagem: str


class DecisaoRoteamento(BaseModel):
    """Submodelo de decisão de roteamento (H2.1.1 T1 / H6.3.1 T1)."""

    destino_principal: Destino | str
    requer_auditoria_humana: bool
    justificativa_roteamento: str
    regra_aplicada: str
    notificacao_gerada: Notificacao | None = None
