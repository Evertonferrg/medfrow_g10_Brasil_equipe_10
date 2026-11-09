"""H4.4.1 T1 — decisão da auditora. H4.4.2 a H4.4.4 reaproveitam este modelo."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class AcaoAuditora(str, Enum):
    APROVAR = "aprovar"
    CORRIGIR = "corrigir"
    REJEITAR = "rejeitar"
    REDIRECIONAR = "redirecionar"


class DecisaoAuditora(BaseModel):
    acao: AcaoAuditora
    auditora: str = Field(min_length=1, max_length=100)
    motivo: str | None = Field(default=None, max_length=500)
    correcoes: dict[str, Any] | None = None
    destino: str | None = None

    @field_validator("auditora")
    @classmethod
    def _nome_simples(cls, v: str) -> str:
        v = v.strip()
        if not v or any(c in v for c in "\r\n\t"):
            raise ValueError("auditora inválida")
        return v

    @model_validator(mode="after")
    def _confere_campos_da_acao(self):
        exigidos = {
            AcaoAuditora.REJEITAR: ("motivo", self.motivo),
            AcaoAuditora.CORRIGIR: ("correcoes", self.correcoes),
            AcaoAuditora.REDIRECIONAR: ("destino", self.destino),
        }
        if self.acao in exigidos and not exigidos[self.acao][1]:
            raise ValueError(f"{self.acao.value} exige {exigidos[self.acao][0]}")
        return self
