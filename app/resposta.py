from . import storage
from .schemas import (
    ArmazenamentoOCI,
    Classificacao,
    DecisaoRoteamento,
    Destino,
    ResultadoTriagem,
)

PASTAS = {
    Destino.FILA_EMERGENCIA_MEDICA.value: "processados/urgentes",
    Destino.FILA_REVISAO_HUMANA.value: "auditoria_humana",
}
PASTA_ROTINA = "processados/rotina"
CAMPOS_FORA = {
    "tipo_documento",
    "especialidade",
    "nivel_prioridade",
    "score_confianca_classificacao",
    "inconsistencias",
}


def montar_resposta(documento_id: str, estado: dict) -> ResultadoTriagem:
    e = estado.get("extracao")
    if "classificacao" in estado:
        classificacao = estado["classificacao"]
    else:
        classificacao = (
            Classificacao(
                tipo_documento=e.tipo_documento,
                especialidade=e.especialidade,
                nivel_prioridade=e.nivel_prioridade,
                score_confianca_classificacao=estado.get("score", 0.0),
            )
            if e
            else None
        )

    decisao = estado.get("decisao_roteamento")
    if not isinstance(decisao, DecisaoRoteamento):
        decisao = DecisaoRoteamento(
            destino_principal=estado["destino"],
            requer_auditoria_humana=estado.get("requer_revisao", False),
            justificativa_roteamento=estado.get("justificativa", ""),
            regra_aplicada=estado.get("regra", "R-ROTEAMENTO"),
            notificacao_gerada=estado.get("notificacao"),
        )

    return ResultadoTriagem(
        status="processado" if e else "erro_extracao",
        documento_id=documento_id,
        classificacao=classificacao,
        dados_extraidos=e.model_dump(exclude=CAMPOS_FORA) if e else None,
        problemas=estado.get("problemas", []),
        decisao_roteamento=decisao,
    )


def _falha(documento_id: str, motivo: str) -> ResultadoTriagem:
    """Resultado fora do formato nunca é entregue: vai para revisão com 'falha de processamento'."""
    return ResultadoTriagem(
        status="erro_processamento",
        documento_id=documento_id,
        problemas=[motivo[:200]],
        decisao_roteamento=DecisaoRoteamento(
            destino_principal=Destino.FILA_REVISAO_HUMANA,
            requer_auditoria_humana=True,
            justificativa_roteamento="Falha de processamento: o resultado não pôde ser montado.",
            regra_aplicada="R-REVISAO",
        ),
    )


def arquivar(documento_id: str, estado: dict) -> dict:
    """Salva o resultado e só DEPOIS preenche o armazenamento na resposta (H5.1.2 T3)."""
    try:
        resultado = montar_resposta(documento_id, estado)
    except Exception as ex:
        resultado = _falha(documento_id, str(ex))
    destino = str(resultado.decisao_roteamento.destino_principal)
    pasta = PASTAS.get(destino, PASTA_ROTINA)
    salvo = storage.salvar(f"{pasta}/{documento_id}.json", resultado.model_dump(mode="json"))
    resultado.armazenamento_oci = ArmazenamentoOCI(
        **salvo, urgente=destino == Destino.FILA_EMERGENCIA_MEDICA.value
    )
    return resultado.model_dump(mode="json")