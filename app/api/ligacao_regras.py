"""H6.1.1 T2 — Rota PUT /regras/limite e consulta de regras."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from app.regras import RegrasConfig, servico_regras

logger = logging.getLogger(__name__)


class AtualizarLimiteRequest(BaseModel):
    limite_confianca: float | None = Field(default=None, ge=0.50, le=0.99)
    limite: float | None = Field(default=None, ge=0.50, le=0.99)
    auditora: str | None = None
    motivo: str | None = None

    @model_validator(mode="after")
    def _verificar_valor(self) -> AtualizarLimiteRequest:
        val = self.limite_confianca if self.limite_confianca is not None else self.limite
        if val is None:
            raise ValueError("limite_confianca ou limite deve ser informado")
        return self

    def valor_limite(self) -> float:
        val = self.limite_confianca if self.limite_confianca is not None else self.limite
        return float(val)


def ligar_regras(app: FastAPI) -> None:
    """Registra as rotas de gerenciamento de regras."""

    @app.get(
        "/regras",
        response_model=RegrasConfig,
        responses={200: {"description": "Configuração completa de regras ativas"}},
    )
    def obter_regras():
        return servico_regras().obter_regras()

    @app.get(
        "/regras/limite",
        responses={200: {"description": "Limite de confiança e versão atuais"}},
    )
    def obter_limite():
        cfg = servico_regras().obter_regras()
        return {
            "limite_confianca": cfg.limite_confianca,
            "versao": cfg.versao,
            "atualizado_por": cfg.atualizado_por,
            "atualizado_em": cfg.atualizado_em,
        }

    @app.put(
        "/regras/limite",
        response_model=RegrasConfig,
        responses={
            200: {"description": "Limite atualizado e nova versão criada"},
            422: {"description": "Limite inválido (deve estar entre 0.50 e 0.99)"},
        },
    )
    def atualizar_limite(
        corpo: AtualizarLimiteRequest | None = None,
        limite: Annotated[float | None, Query(ge=0.50, le=0.99)] = None,
        limite_confianca: Annotated[float | None, Query(ge=0.50, le=0.99)] = None,
        auditora: Annotated[str | None, Query()] = None,
    ):
        valor = None
        nome_auditora = "auditora"
        motivo = None

        if corpo is not None:
            valor = corpo.valor_limite()
            nome_auditora = corpo.auditora or nome_auditora
            motivo = corpo.motivo
        elif limite_confianca is not None:
            valor = limite_confianca
            nome_auditora = auditora or nome_auditora
        elif limite is not None:
            valor = limite
            nome_auditora = auditora or nome_auditora
        else:
            return JSONResponse(
                status_code=422,
                content={"detail": "limite_confianca é obrigatório (entre 0.50 e 0.99)"},
            )

        try:
            nova_config = servico_regras().atualizar_limite(
                novo_limite=valor,
                auditora=nome_auditora,
                motivo=motivo,
            )
            return nova_config
        except ValueError as e:
            return JSONResponse(
                status_code=422,
                content={"detail": str(e)},
            )

