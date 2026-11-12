"""H5.2.2 T1 — Modelo de Evento padronizado para rastreabilidade e histórico."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

TipoEvento = Literal[
    "recebimento",
    "classificacao",
    "extracao",
    "decisao",
    "destino",
    "revisao",
]

AutorTipo = Literal["agente", "auditora", "sistema"]


class Evento(BaseModel):
    """Evento padronizado na linha do tempo de um documento."""
    tipo: str
    data_hora: str = Field(description="Data e hora em formato ISO 8601")
    autor: str = Field(default="agente", description="Autor do evento (agente, auditora, etc)")
    detalhe: str | None = Field(default=None, description="Detalhes ou justificativa do evento")
    hash: str | None = Field(default=None, description="Hash de integridade do evento")
    hash_anterior: str | None = Field(default=None, description="Hash do evento anterior")
    extra: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais do evento")
