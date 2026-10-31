import logging
import os

from . import config, storage
from .schemas import (
    ArmazenamentoOCI,
    Classificacao,
    DecisaoRoteamento,
    Notificacao,
    ResultadoTriagem,
)

PASTA_URGENTES = "processados/urgentes"
PASTA_ROTINA = "processados/rotina"
PASTA_REVISAO = "auditoria_humana"
PASTAS = {
    "Fila_Emergencia_Medica": PASTA_URGENTES,
    "Fila_Revisao_Humana": PASTA_REVISAO,
}
PASTAS_RESULTADO = (PASTA_URGENTES, PASTA_ROTINA, PASTA_REVISAO)
CAMPOS_FORA = {
    "tipo_documento",
    "especialidade",
    "nivel_prioridade",
    "score_confianca_classificacao",
    "inconsistencias",
}

logger = logging.getLogger(__name__)


def montar_resposta(documento_id: str, estado: dict) -> ResultadoTriagem:
    e = estado.get("extracao")
    # a classificação vem do nó 'classificar'. Se o estado não tiver a
    # chave (caminhos antigos), monta a partir da extração como antes.
    if "classificacao" in estado:
        classificacao = estado["classificacao"]
    else:
        classificacao = (
            Classificacao(
                tipo_documento=e.tipo_documento,
                especialidade=e.especialidade,
                nivel_prioridade=e.nivel_prioridade,
                score_confianca_classificacao=estado["score"],
            )
            if e
            else None
        )
    return ResultadoTriagem(
        status="processado" if e else "erro_extracao",
        documento_id=documento_id,
        classificacao=classificacao,  # nosso score, não o do LLM
        dados_extraidos=e.model_dump(exclude=CAMPOS_FORA) if e else None,
        problemas=estado.get("problemas", []),
        decisao_roteamento=DecisaoRoteamento(
            destino_principal=estado["destino"],
            requer_auditoria_humana=estado["requer_revisao"],
            justificativa_roteamento=estado["justificativa"],
            regra_aplicada=estado["regra"],
            notificacao_gerada=estado.get("notificacao"),
        ),
    )


def falha_de_processamento(
    documento_id: str,
    motivo: str,
    justificativa: str | None = None,
    notificacao: Notificacao | None = None,
) -> ResultadoTriagem:
    """Resultado fora do formato nunca é entregue (H2.3.1): vai para a revisão humana
    com o motivo 'falha de processamento', sem dados parciais."""
    return ResultadoTriagem(
        status="erro_processamento",
        documento_id=documento_id,
        problemas=[motivo[:200]],
        decisao_roteamento=DecisaoRoteamento(
            destino_principal="Fila_Revisao_Humana",
            requer_auditoria_humana=True,
            justificativa_roteamento=(
                justificativa
                or "Enviado à revisão humana (regra R-REVISAO): falha de processamento."
            ),
            regra_aplicada="R-REVISAO",
            notificacao_gerada=notificacao,
        ),
    )


_falha = falha_de_processamento  # nome antigo, mantido para imports existentes


def _urgente(resultado: ResultadoTriagem) -> bool:
    """H5.1.2 T3: 'urgente' vem de nivel_prioridade = "Urgente" (ou do destino de emergência)."""
    c = resultado.classificacao
    return bool(
        (c is not None and c.nivel_prioridade == "Urgente")
        or resultado.decisao_roteamento.destino_principal == "Fila_Emergencia_Medica"
    )


def salvar_resultado(
    documento_id: str, resultado: ResultadoTriagem
) -> ArmazenamentoOCI:
    """H5.1.2 T2: grava o ResultadoTriagem completo e SÓ DEPOIS devolve o armazenamento.

    Se a gravação falhar, a exceção sobe e nenhuma resposta com caminho/status é montada.
    """
    pasta = PASTAS.get(resultado.decisao_roteamento.destino_principal, PASTA_ROTINA)
    salvo = storage.salvar(
        f"{pasta}/{documento_id}.json", resultado.model_dump(mode="json")
    )
    return ArmazenamentoOCI(**salvo, urgente=_urgente(resultado))


def arquivar(documento_id: str, estado: dict) -> dict:
    """Pega o resultado montado pelo grafo (nó montar_resultado), salva e devolve a resposta."""
    if estado.get("resultado"):
        resultado = ResultadoTriagem.model_validate(estado["resultado"])
    else:  # caminho da falha dentro de processar(): o grafo nem terminou
        try:
            resultado = montar_resposta(documento_id, estado)
        except Exception as ex:
            logger.exception(...)
            resultado = falha_de_processamento(documento_id, str(ex))
    resultado.armazenamento_oci = salvar_resultado(documento_id, resultado)
    return resultado.model_dump(mode="json")


def carregar_resultado(documento_id: str) -> dict | None:
    """Lê o resultado salvo, valida no formato combinado e preenche o armazenamento.

    Devolve None se não houver resultado. Levanta pydantic.ValidationError se o que está
    salvo estiver fora do formato (a rota responde 500 em vez de entregar dado quebrado).
    """
    for pasta in PASTAS_RESULTADO:
        caminho = f"{pasta}/{documento_id}.json"
        bruto = storage.ler(caminho)
        if bruto is None:
            continue
        resultado = ResultadoTriagem.model_validate_json(bruto)
        resultado.armazenamento_oci = ArmazenamentoOCI(
            bucket=config.bucket(),
            caminho_objeto=caminho,
            status_backup="sucesso",
            local="oci" if os.getenv("OCI_NAMESPACE") else "disco",
            urgente=_urgente(resultado),
        )
        return resultado.model_dump(mode="json")
    return None
