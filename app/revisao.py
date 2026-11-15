"""H4.4.1 / H4.4.2 / H5.1.3 — decisão da auditora sobre um caso em revisão.

A lógica não conhece o storage nem o grafo: recebe `Colaboradores` (armazenamento,
eventos e duas funções). Os testes usam dublês. A ligação de produção está no fim do
arquivo (`colaboradores_padrao`): armazenamento = app.storage (com `mover`, que usa
rename_object no OCI), `calcular_destino` = destino do roteamento sem os motivos de
revisão (H4.4.1 T2/T3) e `validar_correcoes` = validador básico (troque pelos
normalizadores de H1.3.2/H4.1.2 se divergirem). Os imports de grafo/storage ficam dentro
das funções para não criar ciclo: grafo -> resposta -> estado_revisao -> revisao.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from pydantic import ValidationError

from app.decisao import AcaoAuditora, DecisaoAuditora
from app.eventos import ServicoEventos, servico_padrao
from app.status import StatusDocumento

logger = logging.getLogger(__name__)


# mesmas pastas de app/resposta.py
PASTA_REVISAO = "auditoria_humana"
PASTA_URGENTES = "processados/urgentes"
PASTA_ROTINA = "processados/rotina"
PASTA_REJEITADOS = "rejeitados"
SUFIXO_ESTADO = ".estado.json"  # estado guardado ao enviar à revisão (H4.4.1 T2)
PASTAS_DO_CICLO = (PASTA_REVISAO, PASTA_URGENTES, PASTA_ROTINA, PASTA_REJEITADOS)
DESTINOS_REDIRECIONAVEIS = frozenset(
    {
        "Farmacia_Hospitalar",
        "Prontuario_Eletronico",
        "Auditoria_Autorizacoes",
        "Fila_Emergencia_Medica",
    }
)


def obter_destinos_redirecionaveis() -> list[str]:
    """H6.3.1 T5: lê os destinos configurados em ServicoRegras, excluindo a revisão humana."""
    try:
        from app.regras import servico_regras

        destinos = servico_regras().obter_regras().destinos
        return [d for d in destinos if d != "Fila_Revisao_Humana"]
    except Exception:  # noqa: BLE001
        return list(DESTINOS_REDIRECIONAVEIS)


REGRA_AUDITORA = "R-AUDITORA"
_TRAVA = threading.Lock()  # uma decisão por vez neste processo


# ---------------------------------------------------------------- erros
class ErroDecisao(Exception):
    pass


class NaoEncontrado(ErroDecisao):
    pass


class DecisaoConflito(ErroDecisao):
    """Caso já decidido (HTTP 409)."""


class DecisaoInvalida(ErroDecisao):
    """HTTP 422. `campo` é preenchido quando o erro é de um campo corrigido."""

    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.campo = campo

    def __str__(self) -> str:
        return f"{self.campo}: {self.mensagem}" if self.campo else self.mensagem


class CorrecaoInvalida(DecisaoInvalida):
    pass


class SemDestinoCalculado(DecisaoInvalida):
    pass


# ---------------------------------------------------------------- portas
class Armazenamento(Protocol):
    def ler(self, caminho: str) -> bytes | str | None: ...
    def salvar(self, caminho: str, conteudo: dict) -> Any: ...
    def mover(self, origem: str, destino: str) -> None: ...  # H5.1.3 T1
    def existe(self, caminho: str) -> bool: ...
    def apagar(self, caminho: str) -> None: ...  # remove o estado auxiliar


@dataclass
class Alteracao:
    campo: str
    anterior: Any
    novo: Any


@dataclass
class Colaboradores:
    armazenamento: Armazenamento
    eventos: ServicoEventos
    calcular_destino: Callable[[dict], str | None]  # resultado -> destino ou None
    validar_correcoes: Callable[[dict, dict], tuple[dict, list[Alteracao]]]
    # H4.4.4 T3 avisa o plantao quando o destino escolhido é a emergência (H3.3.1)
    alerta_plantao: Callable[[dict], None] | None = None


# ---------------------------------------------------------------- correções (H4.4.2 T2)
CAMPOS_EDITAVEIS = {
    "crm": ("medico_solicitante", "crm"),
    "medico_nome": ("medico_solicitante", "nome"),
    "paciente_nome": ("paciente", "nome"),
    "idade": ("paciente", "idade"),
    "data_nascimento": ("paciente", "data_nascimento"),
    "diagnostico_principal": ("diagnostico_principal",),
    "cid": ("cid",),
}


def _crm(valor) -> str:
    from app.validacao import normalizar_crm  # import local: evita ciclo de imports

    normal = normalizar_crm(str(valor))
    if normal is None:
        raise ValueError("CRM inválido: informe número e UF, como 145892-SP")
    return normal


def _idade(valor) -> int:
    try:
        n = int(str(valor).strip())
    except ValueError:
        raise ValueError("idade deve ser um número") from None
    if not 0 <= n <= 120:
        raise ValueError("idade fora do intervalo 0 a 120")
    return n


def _data(valor) -> str:
    t = str(valor).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(t, formato).date()
        except ValueError:
            continue
        if d > date.today():
            raise ValueError("data de nascimento no futuro")
        return d.strftime("%d/%m/%Y")
    raise ValueError("data inválida (use dd/mm/aaaa)")


def _cid(valor) -> str:
    t = str(valor).upper().strip()
    if not re.fullmatch(r"[A-Z]\d{2}(\.\d{1,2})?", t):
        raise ValueError("CID em formato inválido (ex.: S72.0)")
    return t


def _texto(valor) -> str:
    t = " ".join(str(valor).split())
    if not 2 <= len(t) <= 200:
        raise ValueError("texto deve ter entre 2 e 200 caracteres")
    return t


_NORMALIZADORES = {
    "crm": _crm,
    "idade": _idade,
    "data_nascimento": _data,
    "cid": _cid,
    "medico_nome": _texto,
    "paciente_nome": _texto,
    "diagnostico_principal": _texto,
}


def _ler(dados: dict, caminho: tuple[str, ...]):
    for chave in caminho:
        dados = (dados or {}).get(chave) if isinstance(dados, dict) else None
    return dados


def _gravar(dados: dict, caminho: tuple[str, ...], valor) -> None:
    for chave in caminho[:-1]:
        dados = dados.setdefault(chave, {})
    dados[caminho[-1]] = valor


def validar_correcoes_basico(
    dados: dict, correcoes: dict
) -> tuple[dict, list[Alteracao]]:
    """Valida e aplica as correções numa CÓPIA dos dados (nada é alterado se algo falhar).
    Substitua pelos normalizadores de H1.3.2 (CRM) e H4.1.2 (ReceitaValidada) quando ligar."""
    novos = copy.deepcopy(dados or {})
    alteracoes = []
    for campo, valor in correcoes.items():
        if campo not in CAMPOS_EDITAVEIS:
            raise CorrecaoInvalida("campo não editável", campo)
        try:
            normal = _NORMALIZADORES[campo](valor)
        except ValueError as e:
            raise CorrecaoInvalida(str(e), campo) from None
        caminho = CAMPOS_EDITAVEIS[campo]
        anterior = _ler(novos, caminho)
        if normal == anterior:
            continue
        alteracoes.append(Alteracao(campo, anterior, normal))
        _gravar(novos, caminho, normal)
        if campo == "cid":  # o resultado espelha cid e cid_sugerido
            _gravar(novos, ("cid_sugerido",), normal)
    if not alteracoes:
        raise DecisaoInvalida("nenhum campo foi alterado")
    return novos, alteracoes


def sobrepor_correcoes(extracao: dict, dados: dict) -> dict:
    """Copia para a extração original os campos editáveis do resultado já corrigido.
    Só toca em chaves que a extração já tem (não cria campos que o modelo não conhece)."""
    novo = copy.deepcopy(extracao)
    for campo, caminho in CAMPOS_EDITAVEIS.items():
        if campo == "cid":
            valor = dados.get("cid_sugerido") or dados.get("cid")
            for chave in ("cid_sugerido", "cid"):
                if valor and chave in novo:
                    novo[chave] = valor
            continue
        valor = _ler(dados, caminho)
        pai = novo
        for chave in caminho[:-1]:
            pai = pai.get(chave) if isinstance(pai, dict) else None
        if valor is not None and isinstance(pai, dict) and caminho[-1] in pai:
            pai[caminho[-1]] = valor
    return novo


# ---------------------------------------------------------------- decisão
def _pasta_final(acao: AcaoAuditora, destino: str | None) -> str:
    if acao is AcaoAuditora.REJEITAR:
        return PASTA_REJEITADOS
    return PASTA_URGENTES if destino == "Fila_Emergencia_Medica" else PASTA_ROTINA


def decidir_caso(
    documento_id: str, decisao: DecisaoAuditora, colab: Colaboradores
) -> dict:
    with _TRAVA:
        try:
            atual = colab.eventos.status_atual(documento_id)
        except ValueError:
            raise NaoEncontrado("documento não encontrado") from None
        if atual not in (None, StatusDocumento.EM_AUDITORIA_HUMANA):
            raise DecisaoConflito("documento já decidido")
        origem = f"{PASTA_REVISAO}/{documento_id}.json"
        bruto = colab.armazenamento.ler(origem)
        if bruto is None:
            raise NaoEncontrado("documento não encontrado")
        resultado = json.loads(bruto)

        acao = decisao.acao
        alteracoes: list[Alteracao] = []
        destino: str | None = None
        if acao is AcaoAuditora.CORRIGIR:
            novos, alteracoes = colab.validar_correcoes(
                resultado.get("dados_extraidos") or {}, decisao.correcoes or {}
            )
            resultado["dados_extraidos"] = novos
        if acao in (AcaoAuditora.APROVAR, AcaoAuditora.CORRIGIR):
            destino = colab.calcular_destino(resultado)
            if not destino:
                raise SemDestinoCalculado(
                    "documento sem destino calculado: não pode ser aprovado, "
                    "corrija os dados ou redirecione"
                )
        elif acao is AcaoAuditora.REDIRECIONAR:
            destinos_permitidos = set(obter_destinos_redirecionaveis()) | set(
                DESTINOS_REDIRECIONAVEIS
            )
            if decisao.destino not in destinos_permitidos:
                raise DecisaoInvalida(f"destino inválido: {decisao.destino}", "destino")
            destino = decisao.destino

        rotulo = {
            AcaoAuditora.APROVAR: "aprovado",
            AcaoAuditora.CORRIGIR: "corrigido e aprovado",
            AcaoAuditora.REDIRECIONAR: "redirecionado",
            AcaoAuditora.REJEITAR: "rejeitado",
        }[acao]
        roteamento = resultado.setdefault("decisao_roteamento", {})
        destino_calculado = None
        if acao is AcaoAuditora.REDIRECIONAR:
            try:  # só para a trilha: o que o roteamento teria escolhido
                destino_calculado = colab.calcular_destino(resultado)
            except DecisaoInvalida:
                destino_calculado = None
        if destino:
            roteamento["destino_principal"] = destino
            roteamento["requer_auditoria_humana"] = False
            roteamento["regra_aplicada"] = REGRA_AUDITORA
        if acao is AcaoAuditora.REJEITAR:  # H4.4.3: sem destino; o analista lê o motivo
            roteamento["requer_auditoria_humana"] = False
            roteamento["regra_aplicada"] = REGRA_AUDITORA
            roteamento["justificativa_roteamento"] = (
                f"Rejeitado pela auditora. Motivo: {decisao.motivo}"
            )
        elif acao is AcaoAuditora.REDIRECIONAR:  # H4.4.4
            roteamento["justificativa_roteamento"] = (
                f"Destino definido pela auditora: {destino}."
            )
        else:
            roteamento["justificativa_roteamento"] = f"Revisão humana: {rotulo}."

        final = f"{_pasta_final(acao, destino)}/{documento_id}.json"
        colab.armazenamento.salvar(
            origem, resultado
        )  # conteúdo novo, ainda em auditoria_humana/
        colab.armazenamento.mover(origem, final)  # H5.1.3 T3: renomear, sem cópia
        colab.armazenamento.apagar(f"{PASTA_REVISAO}/{documento_id}{SUFIXO_ESTADO}")

        for alt in alteracoes:  # H4.4.2 T4: um registro por campo alterado
            colab.eventos.registrar_decisao(
                documento_id,
                StatusDocumento.EM_AUDITORIA_HUMANA,
                autor_tipo="auditora",
                autor_nome=decisao.auditora,
                regra_aplicada=REGRA_AUDITORA,
                campo=alt.campo,
                valor_anterior=alt.anterior,
                valor_novo=alt.novo,
                detalhe="correção",
            )
        if acao is AcaoAuditora.REDIRECIONAR:  # H4.4.4: a mudança aparece na trilha
            colab.eventos.registrar_decisao(
                documento_id,
                StatusDocumento.EM_AUDITORIA_HUMANA,
                autor_tipo="auditora",
                autor_nome=decisao.auditora,
                campo="destino",
                valor_anterior=destino_calculado,
                valor_novo=destino,
                detalhe="destino definido pela auditora",
            )
        colab.eventos.registrar_decisao(
            documento_id,
            StatusDocumento.REJEITADO
            if acao is AcaoAuditora.REJEITAR
            else StatusDocumento.PROCESSADO,
            autor_tipo="auditora",
            autor_nome=decisao.auditora,
            regra_aplicada=REGRA_AUDITORA,
            detalhe=f"{rotulo}" + (f": {decisao.motivo}" if decisao.motivo else ""),
        )
        alertado = False

        alerta = getattr(colab, "alertar_plantao", None) or getattr(
            colab, "alerta_plantao", None
        )

        if destino == "Fila_Emergencia_Medica" and alerta:
            try:  # o alerta não pode desfazer uma decisão já gravada
                alerta(resultado)
                alertado = True
            except Exception:
                logger.exception("Falha ao alertar o plantão")

        return {
            "documento_id": documento_id,
            "acao": acao.value,
            "destino": destino,
            "caminho": final,
            "plantao_alertado": alertado,
        }


def prefixos_do_documento(armazenamento: Armazenamento, documento_id: str) -> list[str]:
    """H5.1.3 T4: onde o ID aparece. O esperado é exatamente um prefixo."""
    return [
        p for p in PASTAS_DO_CICLO if armazenamento.existe(f"{p}/{documento_id}.json")
    ]


# ---------------------------------------------------------------- ligação de produção
def calcular_destino_real(resultado: dict) -> str | None:
    """Destino do roteamento ignorando os motivos de revisão (urgência continua valendo).

    Reconstrói a extração guardada ao enviar à revisão, aplica as correções da auditora e
    revalida com o mesmo modelo Extracao. Sem estado guardado (caso antigo): None.
    """
    # imports aqui dentro: grafo.py importa resposta.py, que importa este módulo
    from app import config, storage
    from app.grafo import destino_sem_revisao
    from app.modelos import Classificacao
    from app.schemas import Extracao

    documento_id = resultado.get("documento_id", "")
    bruto = storage.ler(f"{PASTA_REVISAO}/{documento_id}{SUFIXO_ESTADO}")
    if bruto is None:
        return None
    estado = json.loads(bruto)
    if not estado.get("extracao") or not estado.get("classificacao"):
        return None
    dados = sobrepor_correcoes(
        estado["extracao"], resultado.get("dados_extraidos") or {}
    )
    try:
        extracao = Extracao.model_validate(dados)
        classificacao = Classificacao.model_validate(estado["classificacao"])
    except ValidationError as e:
        erro = e.errors()[0]
        campo = ".".join(str(p) for p in erro["loc"])
        raise DecisaoInvalida(
            f"dados corrigidos inválidos: {erro['msg']}", campo
        ) from e
    limite = estado.get("limite_confianca") or config.limite_confianca()
    return destino_sem_revisao(extracao, classificacao, limite)


def colaboradores_padrao() -> Colaboradores:
    from app import storage
    from app.notificacao import alertar_plantao_revisao  # H3.3.2

    # validar_correcoes: troque pelos normalizadores de H1.3.2 (CRM) e H4.1.2 se divergirem
    return Colaboradores(
        armazenamento=storage,
        eventos=servico_padrao(),
        calcular_destino=calcular_destino_real,
        validar_correcoes=validar_correcoes_basico,
        alerta_plantao=alertar_plantao_revisao,  # H3.3.2: avisa o plantão após a decisão
    )
