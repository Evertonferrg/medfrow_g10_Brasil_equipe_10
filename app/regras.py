"""H6.1.1 T1 — Serviço de regras dinâmicas e modelo RegrasConfig.

Gerencia as regras de triagem do MediFlow. Lê a configuração ativa do storage
(bucket OCI ou storage local) a cada execução do grafo, com fallback para o
arquivo padrão do repositório (config/regras.json).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app import config, storage

logger = logging.getLogger(__name__)

CAMINHO_REGRAS_STORAGE = "regras/config.json"
CAMINHO_VERSOES_STORAGE = "regras/versoes"


class RegrasConfig(BaseModel):
    """Modelo das regras de triagem configuráveis (H6.1.1 T1)."""

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
    destinos: list[str] = Field(
        default_factory=lambda: [
            "Farmacia_Hospitalar",
            "Auditoria_Autorizacoes",
            "Prontuario_Eletronico",
            "Fila_Emergencia_Medica",
            "Fila_Revisao_Humana",
        ]
    )
    formatos_aceitos: list[str] = Field(default_factory=lambda: ["PDF", "JPG", "PNG"])
    tamanho_maximo_mb: int = Field(default=10)
    versao: str = "v1"
    atualizado_por: str | None = None
    atualizado_em: str | None = None


def _proxima_versao(versao_atual: str) -> str:
    """Calcula o identificador da próxima versão (v1 -> v2, etc.)."""
    m = re.match(r"^v(\d+)$", versao_atual.strip())
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

        # Salva versão anterior no histórico se ainda não existir
        caminho_v_anterior = f"{CAMINHO_VERSOES_STORAGE}/{atual.versao}.json"
        if not storage.existe(caminho_v_anterior):
            storage.salvar(
                caminho_v_anterior,
                atual.model_dump_json(indent=2).encode("utf-8"),
                sobrescrever=True,
            )

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


_instancia_servico: ServicoRegras | None = None


def servico_regras() -> ServicoRegras:
    """Devolve a instância padrão do ServicoRegras."""
    global _instancia_servico
    if _instancia_servico is None:
        _instancia_servico = ServicoRegras()
    return _instancia_servico
