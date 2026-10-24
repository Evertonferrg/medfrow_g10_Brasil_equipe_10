
from . import storage
from .schemas import (ResultadoTriagem, Classificacao, DecisaoRoteamento, ArmazenamentoOCI)

PASTAS = {"Fila_Emergencia_Medica": "processados/urgentes",
          "Fila_Revisao_Humana": "auditoria_humana"}
PASTA_ROTINA = "processados/rotina"
CAMPOS_FORA = {"tipo_documento", "especialidade", "nivel_prioridade",
               "score_confianca_classificacao", "inconsistencias"}


def montar_resposta(documento_id: str, estado: dict) -> ResultadoTriagem:
    e = estado.get("extracao")
    # a classificação vem do nó 'classificar'. Se o estado não tiver a
    # chave (caminhos antigos), monta a partir da extração como antes.
    if "classificacao" in estado:
        classificacao = estado["classificacao"]
    else:
        classificacao = Classificacao(
            tipo_documento=e.tipo_documento, especialidade=e.especialidade,
            nivel_prioridade=e.nivel_prioridade,
            score_confianca_classificacao=estado["score"]) if e else None
    return ResultadoTriagem(
        status="processado" if e else "erro_extracao",
        documento_id=documento_id,
        classificacao=classificacao,   # nosso score, não o do LLM
        dados_extraidos=e.model_dump(exclude=CAMPOS_FORA) if e else None,
        problemas=estado.get("problemas", []),
        decisao_roteamento=DecisaoRoteamento(
            destino_principal=estado["destino"],
            requer_auditoria_humana=estado["requer_revisao"],
            justificativa_roteamento=estado["justificativa"],
            regra_aplicada=estado["regra"],
            notificacao_gerada=estado.get("notificacao")),
    )


def _falha(documento_id: str, motivo: str) -> ResultadoTriagem:
    """Resultado fora do formato nunca é entregue: vai para revisão com 'falha de processamento'."""
    return ResultadoTriagem(
        status="erro_processamento", documento_id=documento_id, problemas=[motivo[:200]],
        decisao_roteamento=DecisaoRoteamento(
            destino_principal="Fila_Revisao_Humana", requer_auditoria_humana=True,
            justificativa_roteamento="Falha de processamento: o resultado não pôde ser montado.",
            regra_aplicada="R-REVISAO"))


def arquivar(documento_id: str, estado: dict) -> dict:
    """Salva o resultado e só DEPOIS preenche o armazenamento na resposta (H5.1.2 T3)."""
    try:
        resultado = montar_resposta(documento_id, estado)
    except Exception as ex:
        resultado = _falha(documento_id, str(ex))
    destino = resultado.decisao_roteamento.destino_principal
    pasta = PASTAS.get(destino, PASTA_ROTINA)
    salvo = storage.salvar(f"{pasta}/{documento_id}.json", resultado.model_dump(mode="json"))
    resultado.armazenamento_oci = ArmazenamentoOCI(
        **salvo, urgente=destino == "Fila_Emergencia_Medica")
    return resultado.model_dump(mode="json")