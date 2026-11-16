"""H6.1.1 T2 / H6.3.1 T1-T3 — Rotas de configuração de regras, destinos e roteamento."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from app.regras import CondicaoRegra, RegraRoteamento, RegrasConfig, servico_regras

logger = logging.getLogger(__name__)


class AtualizarLimiteRequest(BaseModel):
    limite_confianca: float | None = Field(default=None, ge=0.50, le=0.99)
    limite: float | None = Field(default=None, ge=0.50, le=0.99)
    auditora: str | None = None
    motivo: str | None = None

    @model_validator(mode="after")
    def _verificar_valor(self) -> AtualizarLimiteRequest:
        val = (
            self.limite_confianca if self.limite_confianca is not None else self.limite
        )
        if val is None:
            raise ValueError("limite_confianca ou limite deve ser informado")
        return self

    def valor_limite(self) -> float:
        val = (
            self.limite_confianca if self.limite_confianca is not None else self.limite
        )
        return float(val)


class CriarDestinoRequest(BaseModel):
    """Payload para criação de novo destino configurável (H6.3.1 T1)."""

    nome: str | None = None
    destino: str | None = None
    auditora: str = "auditora"

    def valor_destino(self) -> str:
        d = self.nome if self.nome is not None else self.destino
        if not d or not str(d).strip():
            raise ValueError("nome ou destino deve ser informado")
        return str(d).strip()


class CriarRegraRequest(BaseModel):
    """Payload para criação de regra de roteamento configurável (H6.3.1 T2)."""

    id: str | None = None
    condicao: CondicaoRegra | dict[str, Any] | None = None
    tipo_condicao: str | None = None
    valor: str | None = None
    destino: str
    descricao: str | None = None
    auditora: str = "auditora"


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
        "/regras/destinos",
        responses={200: {"description": "Lista de destinos configurados"}},
    )
    def listar_destinos():
        cfg = servico_regras().obter_regras()
        return {"destinos": cfg.destinos, "versao": cfg.versao}

    @app.post(
        "/regras/destinos",
        response_model=RegrasConfig,
        responses={
            200: {"description": "Destino criado com sucesso"},
            422: {"description": "Nome de destino inválido"},
        },
    )
    def criar_destino(
        corpo: CriarDestinoRequest | None = None,
        nome: Annotated[str | None, Query()] = None,
        destino: Annotated[str | None, Query()] = None,
        auditora: Annotated[str | None, Query()] = None,
    ):
        nome_final = None
        nome_auditora = "auditora"

        if corpo is not None:
            try:
                nome_final = corpo.valor_destino()
            except ValueError as e:
                return JSONResponse(status_code=422, content={"detail": str(e)})
            nome_auditora = corpo.auditora or nome_auditora
        elif nome is not None and str(nome).strip():
            nome_final = str(nome).strip()
            nome_auditora = auditora or nome_auditora
        elif destino is not None and str(destino).strip():
            nome_final = str(destino).strip()
            nome_auditora = auditora or nome_auditora
        else:
            return JSONResponse(
                status_code=422,
                content={"detail": "nome do destino é obrigatório"},
            )

        try:
            nova_config = servico_regras().criar_destino(
                novo_destino=nome_final,
                auditora=nome_auditora,
            )
            return nova_config
        except ValueError as e:
            return JSONResponse(status_code=422, content={"detail": str(e)})

    @app.get(
        "/regras/roteamento",
        responses={200: {"description": "Lista de regras de roteamento ativas"}},
    )
    def listar_regras_roteamento():
        cfg = servico_regras().obter_regras()
        return {
            "regras": [r.model_dump() for r in cfg.regras_roteamento],
            "versao": cfg.versao,
        }

    @app.post(
        "/regras/roteamento",
        response_model=RegrasConfig,
        responses={
            200: {"description": "Regra de roteamento criada com sucesso"},
            422: {"description": "Destino inexistente ou condição inválida"},
        },
    )
    def criar_regra_roteamento(corpo: CriarRegraRequest):
        try:
            # Monta condicao caso venha fragmentada
            cond = corpo.condicao
            if cond is None:
                if not corpo.tipo_condicao or not corpo.valor:
                    return JSONResponse(
                        status_code=422,
                        content={"detail": "tipo_condicao e valor são obrigatórios"},
                    )
                cond = CondicaoRegra(tipo=corpo.tipo_condicao, valor=corpo.valor)  # type: ignore[arg-type]
            elif isinstance(cond, dict):
                cond = CondicaoRegra.model_validate(cond)

            destino_limpo = str(corpo.destino).strip()
            if not destino_limpo:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "destino é obrigatório"},
                )

            # Verifica se destino existe
            cfg_atual = servico_regras().obter_regras()
            if destino_limpo not in cfg_atual.destinos:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": f"Destino '{destino_limpo}' não existe na lista de destinos configurados"
                    },
                )

            kwargs_regra: dict[str, Any] = {
                "condicao": cond,
                "destino": destino_limpo,
                "descricao": corpo.descricao,
            }
            if corpo.id:
                kwargs_regra["id"] = corpo.id

            regra_obj = RegraRoteamento(**kwargs_regra)
            nova_config = servico_regras().adicionar_regra_roteamento(
                regra=regra_obj,
                auditora=corpo.auditora,
            )
            return nova_config
        except ValueError as e:
            return JSONResponse(status_code=422, content={"detail": str(e)})

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
                content={
                    "detail": "limite_confianca é obrigatório (entre 0.50 e 0.99)"
                },
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
