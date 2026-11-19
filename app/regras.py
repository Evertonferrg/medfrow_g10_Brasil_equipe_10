"""
H6.4.1:
- Registra cada versão antes de atualizar a configuração ativa.
- Guarda autor, data, configuração e diferenças campo a campo.
- Lista versões anteriores.
- Permite restaurar uma versão sem apagar o histórico.
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


class AchadoCritico(BaseModel):
    """Achado crítico que torna um documento Urgente (H6.2.1)."""

    nome: str
    sinonimos: list[str] = Field(default_factory=list)

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, v: Any) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("Nome do achado crítico não pode ser vazio")
        return s

    @field_validator("sinonimos", mode="before")
    @classmethod
    def _normalizar_sinonimos(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(p).strip() for p in v if str(p).strip()]
        return []

    @model_validator(mode="after")
    def _garantir_nome_em_sinonimos(self) -> AchadoCritico:
        if self.nome and self.nome not in self.sinonimos:
            self.sinonimos = [self.nome, *self.sinonimos]
        return self


ACHADOS_CRITICOS_PADRAO: list[AchadoCritico] = [
    AchadoCritico(
        nome="TEP",
        sinonimos=["TEP", "tromboembolismo pulmonar", "embolia pulmonar"],
    ),
    AchadoCritico(
        nome="IAM",
        sinonimos=["IAM", "infarto agudo do miocárdio", "infarto do miocárdio"],
    ),
    AchadoCritico(
        nome="AVC",
        sinonimos=[
            "AVC",
            "AVCI",
            "AVCH",
            "acidente vascular cerebral",
            "acidente vascular encefálico",
        ],
    ),
    AchadoCritico(
        nome="Sepse",
        sinonimos=["sepse", "choque séptico", "sepsis"],
    ),
    AchadoCritico(
        nome="Dissecção de aorta",
        sinonimos=[
            "dissecção de aorta",
            "dissecção aórtica",
            "dissecção aguda de aorta",
        ],
    ),
    AchadoCritico(
        nome="Hemorragia intracraniana",
        sinonimos=[
            "hemorragia intracraniana",
            "hemorragia intracerebral",
            "hemorragia subaracnóidea",
            "hematoma intracraniano",
        ],
    ),
]


class TipoCondicao(str, Enum):
    """Conjunto fechado de condições de regras de roteamento (H6.3.1 T2)."""

    TIPO_DOCUMENTO_IGUAL = "tipo_documento_igual"
    CID_COMECA_COM = "cid_comeca_com"


class CondicaoRegra(BaseModel):
    """Condição restrita a um conjunto fechado: nunca executa código livre."""

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
            f"Tipo de condição '{v}' inválido. Condições permitidas: "
            "'tipo_documento_igual', 'cid_comeca_com'."
        )

    @field_validator("valor")
    @classmethod
    def _validar_valor(cls, v: str) -> str:
        v_limpo = str(v).strip()

        if not v_limpo:
            raise ValueError("O valor da condição não pode ser vazio.")

        return v_limpo


class RegraRoteamento(BaseModel):
    """Modelo da regra de roteamento configurável."""

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
    """Modelo das regras de triagem configuráveis."""

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

    achados_criticos: list[AchadoCritico] = Field(
        default_factory=lambda: [a.model_copy() for a in ACHADOS_CRITICOS_PADRAO],
        min_length=1,
    )

    versao: str = "v1"
    atualizado_por: str | None = None
    atualizado_em: str | None = None

    @field_validator("achados_criticos", mode="before")
    @classmethod
    def _pre_validar_achados(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, list):
            if len(v) == 0:
                raise ValueError("A lista de achados críticos não pode ficar vazia")
            return v
        if isinstance(v, dict):
            itens = []
            for k, val in v.items():
                sin = val if isinstance(val, list) else [str(val)]
                itens.append({"nome": k, "sinonimos": sin})
            if not itens:
                raise ValueError("A lista de achados críticos não pode ficar vazia")
            return itens
        return v

    @field_validator("achados_criticos")
    @classmethod
    def _validar_achados_criticos(
        cls, achados: list[AchadoCritico]
    ) -> list[AchadoCritico]:
        if not achados or len(achados) == 0:
            raise ValueError("A lista de achados críticos não pode ficar vazia")
        return achados

    @field_validator("destinos")
    @classmethod
    def _validar_destinos(cls, destinos: list[str]) -> list[str]:
        faltando = [d for d in DESTINOS_OFICIAIS if d not in destinos]

        if faltando:
            raise ValueError(
                "Os destinos oficiais do edital são fixos e não podem "
                f"ser removidos: {', '.join(faltando)}"
            )

        destinos_limpos: list[str] = []

        for destino in destinos:
            destino_str = str(destino).strip()

            if not destino_str:
                raise ValueError("Nome de destino não pode ser vazio")

            if destino_str not in destinos_limpos:
                destinos_limpos.append(destino_str)

        return destinos_limpos

    @model_validator(mode="after")
    def _validar_regras_roteamento(self) -> RegrasConfig:
        destinos_set = set(self.destinos)

        for regra in self.regras_roteamento:
            if regra.destino not in destinos_set:
                raise ValueError(
                    f"Destino '{regra.destino}' da regra '{regra.id}' "
                    "não existe na lista de destinos configurados"
                )

        return self


def _proxima_versao(versao_atual: str) -> str:
    """Calcula o identificador da próxima versão."""

    match = re.match(r"^v(\d+)$", str(versao_atual).strip())

    if match:
        return f"v{int(match.group(1)) + 1}"

    return "v2"


class ServicoRegras:
    """Serviço responsável por ler, atualizar e versionar as regras."""

    def __init__(self, caminho_storage: str = CAMINHO_REGRAS_STORAGE):
        self.caminho_storage = caminho_storage

    def obter_regras(self) -> RegrasConfig:
        """Lê as regras do storage, usando o arquivo do repositório como fallback."""

        try:
            bruto = storage.ler(self.caminho_storage)

            if bruto:
                texto = bruto.decode("utf-8") if isinstance(bruto, bytes) else bruto

                dados = json.loads(texto)

                if isinstance(dados, dict):
                    return RegrasConfig.model_validate(dados)

        except Exception:
            logger.exception("Falha ao ler regras do storage; usando arquivo padrão")

        dados_repo = config.carregar_regras()

        if dados_repo:
            try:
                dados_repo.setdefault("versao", "v1")
                return RegrasConfig.model_validate(dados_repo)

            except Exception:
                logger.exception("Arquivo de regras do repositório inválido")

        return RegrasConfig()

    def _caminho_versao(self, versao: str) -> str:
        """Monta o caminho seguro de uma versão."""

        if not re.fullmatch(r"v\d+", str(versao)):
            raise ValueError(f"Identificador de versão inválido: {versao}")

        return f"{CAMINHO_VERSOES_STORAGE}/{versao}.json"

    @staticmethod
    def _dados_comparaveis(regras: RegrasConfig) -> dict:
        """Retorna os campos de configuração, sem metadados da versão."""

        return regras.model_dump(
            mode="json",
            exclude={
                "versao",
                "atualizado_por",
                "atualizado_em",
            },
        )

    @classmethod
    def _calcular_diferencas(
        cls,
        anterior: RegrasConfig,
        nova: RegrasConfig,
    ) -> dict:
        """Calcula as diferenças campo a campo entre duas configurações."""

        dados_anteriores = cls._dados_comparaveis(anterior)
        dados_novos = cls._dados_comparaveis(nova)

        diferencas = {}

        for campo in sorted(set(dados_anteriores) | set(dados_novos)):
            valor_anterior = dados_anteriores.get(campo)
            valor_novo = dados_novos.get(campo)

            if valor_anterior != valor_novo:
                diferencas[campo] = {
                    "anterior": valor_anterior,
                    "novo": valor_novo,
                }

        return diferencas

    def _proxima_versao_disponivel(
        self,
        versao_atual: str,
    ) -> str:
        """Evita reutilizar identificadores já existentes no histórico."""

        numeros = []

        for caminho in storage.listar(f"{CAMINHO_VERSOES_STORAGE}/"):
            nome = caminho.rsplit("/", 1)[-1]

            match = re.fullmatch(r"v(\d+)\.json", nome)

            if match:
                numeros.append(int(match.group(1)))

        match_atual = re.fullmatch(
            r"v(\d+)",
            str(versao_atual),
        )

        if match_atual:
            numeros.append(int(match_atual.group(1)))

        return f"v{max(numeros, default=1) + 1}"

    def _gravar_registro_versao(
        self,
        regras: RegrasConfig,
        diferencas: dict | None = None,
    ) -> None:
        """Grava uma versão histórica sem permitir sobrescrita."""

        registro = {
            "versao": regras.versao,
            "autor": regras.atualizado_por or "sistema",
            "data": regras.atualizado_em or datetime.now(UTC).isoformat(),
            "diferencas": diferencas or {},
            "configuracao": regras.model_dump(mode="json"),
        }

        storage.salvar(
            self._caminho_versao(regras.versao),
            registro,
            sobrescrever=False,
        )

    def salvar_regras(self, regras: RegrasConfig) -> None:
        """Registra o histórico antes de atualizar a configuração ativa.

        Mantém compatibilidade com a inicialização usada pelos testes.
        """

        self._gravar_registro_versao(regras)

        payload = regras.model_dump_json(indent=2).encode("utf-8")

        storage.salvar(
            self.caminho_storage,
            payload,
            sobrescrever=True,
        )

    def _registrar_alteracao(
        self,
        atual: RegrasConfig,
        nova: RegrasConfig,
    ) -> None:
        """Registra a alteração antes de atualizar as regras ativas."""

        caminho_anterior = self._caminho_versao(atual.versao)

        # Preserva a versão anterior caso ela ainda não esteja no histórico.
        if not storage.existe(caminho_anterior):
            self._gravar_registro_versao(atual)

        diferencas = self._calcular_diferencas(atual, nova)

        # Primeiro grava o histórico da nova versão.
        self._gravar_registro_versao(nova, diferencas)

        # Só depois atualiza a configuração ativa.
        payload = nova.model_dump_json(indent=2).encode("utf-8")

        storage.salvar(
            self.caminho_storage,
            payload,
            sobrescrever=True,
        )

    def listar_versoes(self) -> list[dict]:
        """Lista versões históricas, aceitando também arquivos antigos."""

        prefixo = f"{CAMINHO_VERSOES_STORAGE}/"
        versoes = []

        for caminho in storage.listar(prefixo):
            if not re.fullmatch(
                rf"{re.escape(prefixo)}v\d+\.json",
                caminho,
            ):
                continue

            bruto = storage.ler(caminho)

            if not bruto:
                continue

            try:
                texto = bruto.decode("utf-8") if isinstance(bruto, bytes) else bruto

                dados = json.loads(texto)

                # Compatibilidade com o histórico antigo, que salvava
                # diretamente o JSON de RegrasConfig.
                if "configuracao" not in dados:
                    configuracao = RegrasConfig.model_validate(dados)

                    registro = {
                        "versao": configuracao.versao,
                        "autor": configuracao.atualizado_por or "sistema",
                        "data": configuracao.atualizado_em,
                        "diferencas": {},
                        "configuracao": configuracao.model_dump(mode="json"),
                    }

                else:
                    configuracao = RegrasConfig.model_validate(dados["configuracao"])

                    registro = {
                        **dados,
                        "configuracao": configuracao.model_dump(mode="json"),
                    }

                versoes.append(registro)

            except Exception:
                logger.exception(
                    "Não foi possível carregar a versão histórica: %s",
                    caminho,
                )

        return sorted(
            versoes,
            key=lambda item: int(item["versao"][1:]),
            reverse=True,
        )

    def restaurar_versao(
        self,
        versao: str,
        auditora: str = "auditora",
    ) -> RegrasConfig:
        """Restaura uma versão histórica criando uma nova versão."""

        if not re.fullmatch(r"v\d+", str(versao)):
            raise ValueError(f"Identificador de versão inválido: {versao}")

        historico = self.listar_versoes()
        registro = next(
            (item for item in historico if item["versao"] == versao),
            None,
        )

        if registro is None:
            raise ValueError(f"Versão histórica '{versao}' não encontrada")

        configuracao_restaurada = RegrasConfig.model_validate(registro["configuracao"])
        atual = self.obter_regras()
        nova_versao = self._proxima_versao_disponivel(atual.versao)

        nova_config = configuracao_restaurada.model_copy(
            update={
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": datetime.now(UTC).isoformat(),
            }
        )

        self._registrar_alteracao(atual, nova_config)
        logger.info(
            "Regras restauradas da versão %s para %s por %s",
            versao,
            nova_versao,
            auditora,
        )
        return nova_config

    def atualizar_limite(
        self,
        novo_limite: float,
        auditora: str = "auditora",
        motivo: str | None = None,
    ) -> RegrasConfig:
        """Atualiza o limite de confiança e cria uma nova versão."""

        if novo_limite < 0.50 or novo_limite > 0.99:
            raise ValueError("limite_confianca deve estar entre 0.50 e 0.99")

        atual = self.obter_regras()

        nova_versao = self._proxima_versao_disponivel(atual.versao)

        agora = datetime.now(UTC).isoformat()

        nova_config = atual.model_copy(
            update={
                "limite_confianca": round(float(novo_limite), 4),
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": agora,
            }
        )

        self._registrar_alteracao(atual, nova_config)

        return nova_config

    def criar_destino(
        self,
        novo_destino: str,
        auditora: str = "auditora",
    ) -> RegrasConfig:
        """Adiciona um novo destino à lista de destinos configuráveis."""

        nome = str(novo_destino).strip()

        if not nome:
            raise ValueError("Nome do destino não pode ser vazio")

        atual = self.obter_regras()

        if nome in atual.destinos:
            return atual

        nova_versao = self._proxima_versao_disponivel(atual.versao)

        agora = datetime.now(UTC).isoformat()

        novos_destinos = list(atual.destinos) + [nome]

        nova_config = atual.model_copy(
            update={
                "destinos": novos_destinos,
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": agora,
            }
        )

        self._registrar_alteracao(atual, nova_config)

        return nova_config

    def adicionar_regra_roteamento(
        self,
        regra: RegraRoteamento,
        auditora: str = "auditora",
    ) -> RegrasConfig:
        """Adiciona ou atualiza uma regra de roteamento."""

        atual = self.obter_regras()

        if regra.destino not in atual.destinos:
            raise ValueError(
                f"Destino '{regra.destino}' não existe "
                "na lista de destinos configurados"
            )

        nova_versao = self._proxima_versao_disponivel(atual.versao)

        agora = datetime.now(UTC).isoformat()

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

        self._registrar_alteracao(atual, nova_config)

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

        nova_versao = self._proxima_versao_disponivel(atual.versao)

        agora = datetime.now(UTC).isoformat()

        novas_regras = [r for r in atual.regras_roteamento if r.id != regra_id]

        nova_config = atual.model_copy(
            update={
                "regras_roteamento": novas_regras,
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": agora,
            }
        )

        self._registrar_alteracao(atual, nova_config)

        return nova_config

    def remover_destino(
        self,
        destino: str,
        auditora: str = "auditora",
    ) -> RegrasConfig:
        """Remove um destino configurado, protegendo os destinos oficiais."""

        nome = str(destino).strip()

        if nome in DESTINOS_OFICIAIS:
            raise ValueError("Destinos oficiais do edital não podem ser removidos")

        atual = self.obter_regras()

        if nome not in atual.destinos:
            return atual

        nova_versao = self._proxima_versao_disponivel(atual.versao)

        agora = datetime.now(UTC).isoformat()

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

        self._registrar_alteracao(atual, nova_config)

        return nova_config

    def atualizar_achados(
        self,
        novos_achados: list[AchadoCritico | dict[str, Any] | str],
        auditora: str = "auditora",
        motivo: str | None = None,
    ) -> RegrasConfig:
        """H6.2.1 T2: Grava a lista de achados críticos e cria uma versão."""
        if not novos_achados or len(novos_achados) == 0:
            raise ValueError("A lista de achados críticos não pode ficar vazia")

        cfg_atual = self.obter_regras()
        achados_convertidos: list[AchadoCritico] = []
        for item in novos_achados:
            if isinstance(item, AchadoCritico):
                achados_convertidos.append(item)
            elif isinstance(item, dict):
                if "nome" in item:
                    nome = str(item["nome"]).strip()
                    if not nome:
                        continue
                    sin = item.get("sinonimos") or []
                    if isinstance(sin, str):
                        sin = [s.strip() for s in sin.split(",") if s.strip()]
                    achados_convertidos.append(AchadoCritico(nome=nome, sinonimos=sin))
                else:
                    for k, v in item.items():
                        sin = v if isinstance(v, list) else [str(v)]
                        achados_convertidos.append(AchadoCritico(nome=k, sinonimos=sin))
            elif isinstance(item, str) and item.strip():
                achados_convertidos.append(
                    AchadoCritico(nome=item.strip(), sinonimos=[item.strip()])
                )

        if not achados_convertidos or len(achados_convertidos) == 0:
            raise ValueError("A lista de achados críticos não pode ficar vazia")

        nova_versao = self._proxima_versao_disponivel(cfg_atual.versao)
        agora = datetime.now(UTC).isoformat()

        nova_config = cfg_atual.model_copy(
            update={
                "achados_criticos": achados_convertidos,
                "versao": nova_versao,
                "atualizado_por": auditora,
                "atualizado_em": agora,
            }
        )

        self._registrar_alteracao(cfg_atual, nova_config)
        return nova_config


_instancia_servico: ServicoRegras | None = None


def servico_regras() -> ServicoRegras:
    """Devolve a instância padrão do ServicoRegras."""

    global _instancia_servico

    if _instancia_servico is None:
        _instancia_servico = ServicoRegras()

    return _instancia_servico
