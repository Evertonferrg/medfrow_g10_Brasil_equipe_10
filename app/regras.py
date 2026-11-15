"""H6.1.1 T1 / H6.3.1 T1-T2 — Serviço de regras dinâmicas e modelos RegrasConfig e RegraRoteamento.

Gerencia as regras de triagem e roteamento do MediFlow. Lê a configuração ativa do storage
(bucket OCI ou storage local) a cada execução do grafo, com fallback para o
arquivo padrão do repositório (config/regras.json).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app import config, storage

logger = logging.getLogger(__name__)

CAMINHO_REGRAS_STORAGE = "regras/config.json"
CAMINHO_VERSOES_STORAGE = "regras/versoes"

DESTINOS_OFICIAIS: list[str] = [
    "Farmacia_Hospitalar",
    "Auditoria_Autorizacoes",
    "Prontuario_Eletronico",
    "Fila_Emergencia_Medica",
    "Fila_Revisao_Humana",
]


class TipoCondicao(str, Enum):
    """Conjunto fechado de condições de regras de roteamento (H6.3.1 T2)."""

    TIPO_DOCUMENTO_IGUAL = "tipo_documento_igual"
    CID_COMECA_COM = "cid_comeca_com"


class CondicaoRegra(BaseModel):
    """Condição restrita a um conjunto fechado: nunca executa código livre (H6.3.1 T2)."""

    tipo: TipoCondicao
    valor: str

    @field_validator("tipo", mode="before")
    @classmethod
    def _normalizar_tipo(cls, v: Any) -> TipoCondicao:
        if isinstance(v, TipoCondicao):
            return v
        v_str = str(v).strip().lower()
        if v_str in (
            "tipo_documento_igual",
            "tipo_documento_igual_a",
            "tipo_documento",
            "tipo",
        ):
            return TipoCondicao.TIPO_DOCUMENTO_IGUAL
        if v_str in (
            "cid_comeca_com",
            "cid_inicia_com",
            "cid_comeca",
            "cid",
        ):
            return TipoCondicao.CID_COMECA_COM
        raise ValueError(
            f"Tipo de condição '{v}' inválido. Condições permitidas: 'tipo_documento_igual', 'cid_comeca_com'."
        )

    @field_validator("valor")
    @classmethod
    def _validar_valor(cls, v: str) -> str:
        v_limpo = str(v).strip()
        if not v_limpo:
            raise ValueError("O valor da condição não pode ser vazio.")
        return v_limpo


class RegraRoteamento(BaseModel):
    """Modelo da regra de roteamento configurável (H6.3.1 T2)."""

    id: str = Field(default_factory=lambda: f"R-{uuid.uuid4().hex[:6].upper()}")
    condicao: CondicaoRegra
    destino: str
    descricao: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _pre_validar(cls, dados: Any) -> Any:
        if (
            isinstance(dados, dict)
            and "condicao" not in dados
            and ("tipo_condicao" in dados or "tipo" in dados)
        ):
            tipo = dados.get("tipo_condicao") or dados.get("tipo")
            valor = dados.get("valor", "")
            dados["condicao"] = {"tipo": tipo, "valor": valor}
        return dados

    @field_validator("destino")
    @classmethod
    def _validar_destino(cls, v: str) -> str:
        v_limpo = str(v).strip()
        if not v_limpo:
            raise ValueError("O destino da regra não pode ser vazio.")
        return v_limpo


class RegrasConfig(BaseModel):
    """Modelo das regras de triagem configuráveis (H6.1.1 T1 / H6.3.1 T1)."""

    limite_confianca: float = Field(default=0.80, ge=0.50, le=0.99)
    campos_criticos: list[str] = Field(
        default_factory=lambda: [
            "paciente.nome",
            "medico_solicitante.crm",
            "medicamentos.nome",
            "medicamentos.dose",
            "cid_sugerido",
        ]
    )
    canais_origem: list[str] = Field(
        default_factory=lambda: [
            "Pronto_Socorro",
            "Ambulatorio",
            "Laboratorio",
            "Operadora",
        ]
    )
    destinos: list[str] = Field(default_factory=lambda: list(DESTINOS_OFICIAIS))
    formatos_aceitos: list[str] = Field(default_factory=lambda: ["PDF", "JPG", "PNG"])
    tamanho_maximo_mb: int = Field(default=10)
    regras_roteamento: list[RegraRoteamento] = Field(default_factory=list)
    versao: str = "v1"
    atualizado_por: str | None = None
    atualizado_em: str | None = None

    @field_validator("destinos")
    @classmethod
    def _validar_destinos(cls, destinos: list[str]) -> list[str]:
        # T1: os cinco destinos oficiais do edital ficam fixos e não podem ser removidos
        faltando = [d for d in DESTINOS_OFICIAIS if d not in destinos]
        if faltando:
            raise ValueError(
                f"Os destinos oficiais do edital são fixos e não podem ser removidos: {', '.join(faltando)}"
            )
        destinos_limpos: list[str] = []
        for d in destinos:
            d_str = str(d).strip()
            if not d_str:
                raise ValueError("Nome de destino não pode ser vazio")
            if d_str not in destinos_limpos:
                destinos_limpos.append(d_str)
        return destinos_limpos

    @model_validator(mode="after")
    def _validar_regras_roteamento(self) -> RegrasConfig:
        destinos_set = set(self.destinos)
        for regra in self.regras_roteamento:
            if regra.destino not in destinos_set:
                raise ValueError(
                    f"Destino '{regra.destino}' da regra '{regra.id}' não existe na lista de destinos configurados"
                )
        return self


def _proxima_versao(versao_atual: str) -> str:
    """Calcula o identificador da próxima versão (v1 -> v2, etc.)."""
    m = re.match(r"^v(\d+)$", str(versao_atual).strip())
    if m:
        return f"v{int(m.group(1)) + 1}"
    return "v2"


class ServicoRegras:
    """Serviço responsável por ler e atualizar as regras de triagem."""

    def __init__(self, caminho_storage: str = CAMINHO_REGRAS_STORAGE):
        self.caminho_storage = caminho_storage

    def obter_regras(self) -> RegrasConfig:
        """Lê do bucket a cada chamada, com o arquivo do repositório como padrão."""
        try:
            bruto = storage.ler(self.caminho_storage)
            if bruto:
                texto = bruto.decode("utf-8") if isinstance(bruto, bytes) else bruto
                dados = json.loads(texto)
                if isinstance(dados, dict):
                    return RegrasConfig.model_validate(dados)
        except Exception:
            logger.exception("Falha ao ler regras do storage; usando arquivo padrão")

        # Fallback para o arquivo do repositório
        dados_repo = config.carregar_regras()
        if dados_repo:
            try:
                dados_repo.setdefault("versao", "v1")
                return RegrasConfig.model_validate(dados_repo)
            except Exception:
                logger.exception("Arquivo de regras do repositório inválido")

        return RegrasConfig()

    def salvar_regras(self, regras: RegrasConfig) -> None:
        """Grava a configuração no storage e registra a versão."""
        payload = regras.model_dump_json(indent=2).encode("utf-8")
        storage.salvar(self.caminho_storage, payload, sobrescrever=True)

        # Salva também no histórico de versões (H6.4.1)
        caminho_versao = f"{CAMINHO_VERSOES_STORAGE}/{regras.versao}.json"
        storage.salvar(caminho_versao, payload, sobrescrever=True)

    def _arquivar_versao(self, atual: RegrasConfig) -> None:
        caminho_v_anterior = f"{CAMINHO_VERSOES_STORAGE}/{atual.versao}.json"
        if not storage.existe(caminho_v_anterior):
            storage.salvar(
                caminho_v_anterior,
                atual.model_dump_json(indent=2).encode("utf-8"),
                sobrescrever=True,
            )

    def atualizar_limite(
        self,
        novo_limite: float,
        auditora: str = "auditora",
        motivo: str | None = None,
    ) -> RegrasConfig:
        """H6.1.1 T2: valida o novo valor, grava a configuração e cria uma nova versão."""
        if novo_limite < 0.50 or novo_limite > 0.99:
            raise ValueError("limite_confianca deve estar entre 0.50 e 0.99")

        atual = self.obter_regras()
        nova_versao = _proxima_versao(atual.versao)
        agora = datetime.now(UTC).isoformat()
        self._arquivar_versao(atual)

        nova_config = atual.model_copy(
            update={
                "limite_confianca": round(float(novo_limite), 4),
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": agora,
            }
        )
        self.salvar_regras(nova_config)
        return nova_config

    def criar_destino(
        self,
        novo_destino: str,
        auditora: str = "auditora",
    ) -> RegrasConfig:
        """H6.3.1 T1: adiciona um novo destino à lista de destinos configuráveis."""
        nome = str(novo_destino).strip()
        if not nome:
            raise ValueError("Nome do destino não pode ser vazio")

        atual = self.obter_regras()
        if nome in atual.destinos:
            return atual

        nova_versao = _proxima_versao(atual.versao)
        agora = datetime.now(UTC).isoformat()
        self._arquivar_versao(atual)

        novos_destinos = list(atual.destinos) + [nome]
        nova_config = atual.model_copy(
            update={
                "destinos": novos_destinos,
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": agora,
            }
        )
        self.salvar_regras(nova_config)
        return nova_config

    def adicionar_regra_roteamento(
        self,
        regra: RegraRoteamento,
        auditora: str = "auditora",
    ) -> RegrasConfig:
        """H6.3.1 T2: adiciona ou atualiza uma regra de roteamento."""
        atual = self.obter_regras()
        if regra.destino not in atual.destinos:
            raise ValueError(
                f"Destino '{regra.destino}' não existe na lista de destinos configurados"
            )

        nova_versao = _proxima_versao(atual.versao)
        agora = datetime.now(UTC).isoformat()
        self._arquivar_versao(atual)

        novas_regras = [r for r in atual.regras_roteamento if r.id != regra.id]
        novas_regras.append(regra)

        nova_config = atual.model_copy(
            update={
                "regras_roteamento": novas_regras,
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": agora,
            }
        )
        self.salvar_regras(nova_config)
        return nova_config

    def remover_regra_roteamento(
        self,
        regra_id: str,
        auditora: str = "auditora",
    ) -> RegrasConfig:
        """Remove uma regra de roteamento pelo identificador."""
        atual = self.obter_regras()
        if not any(r.id == regra_id for r in atual.regras_roteamento):
            return atual

        nova_versao = _proxima_versao(atual.versao)
        agora = datetime.now(UTC).isoformat()
        self._arquivar_versao(atual)

        novas_regras = [r for r in atual.regras_roteamento if r.id != regra_id]
        nova_config = atual.model_copy(
            update={
                "regras_roteamento": novas_regras,
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": agora,
            }
        )
        self.salvar_regras(nova_config)
        return nova_config

    def remover_destino(
        self,
        destino: str,
        auditora: str = "auditora",
    ) -> RegrasConfig:
        """Remove um destino configurado (destinos oficiais são protegidos)."""
        nome = str(destino).strip()
        if nome in DESTINOS_OFICIAIS:
            raise ValueError("Destinos oficiais do edital não podem ser removidos")

        atual = self.obter_regras()
        if nome not in atual.destinos:
            return atual

        nova_versao = _proxima_versao(atual.versao)
        agora = datetime.now(UTC).isoformat()
        self._arquivar_versao(atual)

        novos_destinos = [d for d in atual.destinos if d != nome]
        novas_regras = [r for r in atual.regras_roteamento if r.destino != nome]

        nova_config = atual.model_copy(
            update={
                "destinos": novos_destinos,
                "regras_roteamento": novas_regras,
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": agora,
            }
        )
        self.salvar_regras(nova_config)
        return nova_config


_instancia_servico: ServicoRegras | None = None


def servico_regras() -> ServicoRegras:
    """Devolve a instância padrão do ServicoRegras."""
    global _instancia_servico
    if _instancia_servico is None:
        _instancia_servico = ServicoRegras()
    return _instancia_servico
