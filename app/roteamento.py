PADRAO = "Prontuario_Eletronico"

# tipo de documento -> (destino, id da regra, descrição da regra)
ROTINA = {
    "Receituário Médico": (
        "Farmacia_Hospitalar",
        "R-RECEITA",
        "receitas de rotina seguem para a farmácia",
    ),
    "Guia de Solicitação de Procedimento": (
        "Auditoria_Autorizacoes",
        "R-GUIA",
        "guias de rotina seguem para a auditoria de autorizações",
    ),
}
REGRA_PRONTUARIO = (
    "R-PRONTUARIO",
    "laudos, altas e atestados de rotina seguem para o prontuário",
)

# H2.2.1 T1: id -> descrição curta de CADA regra de decisão (fonte única dos textos)
REGRAS = {
    "R-REVISAO": "qualquer dúvida na leitura ou na classificação exige revisão humana",
    "R-URGENCIA": "urgência tem precedência sobre a rota de rotina",
    REGRA_PRONTUARIO[0]: REGRA_PRONTUARIO[1],
    **{regra: descricao for _, regra, descricao in ROTINA.values()},
}


def descricao_regra(regra: str) -> str:
    """Descrição curta da regra (ex.: 'R-RECEITA' -> 'receitas de rotina seguem para a farmácia')."""
    return REGRAS.get(regra, "")


def decidir_destino(tipo: str, prioridade: str, requer_revisao: bool):
    """Devolve (destino, regra). A ORDEM importa: segurança, urgência, rotina.

    A descrição da regra sai de descricao_regra(regra).
    """
    if requer_revisao:
        return "Fila_Revisao_Humana", "R-REVISAO"
    if prioridade == "Urgente":
        return "Fila_Emergencia_Medica", "R-URGENCIA"
    if tipo in ROTINA:
        destino, regra, _ = ROTINA[tipo]
        return destino, regra
    return PADRAO, REGRA_PRONTUARIO[0]


def _motivos(motivo, problemas, erro, score) -> list:
    """H2.2.1 T3: motivos acumulados no estado, sem repetir (ex.: 'ilegível' + 'ilegível: borrada')."""
    partes = []
    if motivo:
        partes.append(str(motivo).strip().rstrip("."))
    for p in problemas or []:
        p = str(p).strip().rstrip(".")
        if not p:
            continue
        if motivo and p.lower().startswith(partes[0].lower()):
            partes[0] = p  # a versão com detalhe substitui o motivo curto
        elif p not in partes:
            partes.append(p)
    if not partes and erro:
        partes.append(f"falha na extração automática ({str(erro)[:80]})")
    if not partes:
        partes.append(f"baixa confiança na classificação ({score})")
    return partes[:4]


def justificativa(
    tipo,
    prioridade,
    score,
    destino,
    regra,
    achado=None,
    problemas=None,
    erro=None,
    motivo=None,
):
    """Justificativa por MODELO DE TEXTO, sem LLM (H2.2.1 T2): nunca contradiz o destino.

    Sempre uma frase só: tipo, prioridade e regra (rota) ou a(s) dúvida(s) (revisão).
    """
    if regra == "R-REVISAO":
        detalhe = "; ".join(_motivos(motivo, problemas, erro, score))
        return f"Enviado à revisão humana (regra R-REVISAO): {detalhe}."
    if regra == "R-URGENCIA":
        return (
            f"{tipo} com prioridade Urgente (achado crítico: {achado}); regra R-URGENCIA: "
            f"{descricao_regra(regra)} → {destino}."
        )
    descricao = descricao_regra(regra) or REGRA_PRONTUARIO[1]
    return (
        f"{tipo} com prioridade {prioridade} e confiança {score}; "
        f"regra {regra}: {descricao} → {destino}."
    )


gerar_justificativa = justificativa  # nome do card H2.2.1 T2
