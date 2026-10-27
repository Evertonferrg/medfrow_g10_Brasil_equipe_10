 
PADRAO = "Prontuario_Eletronico"
 
# tipo de documento -> (destino, id da regra, descrição da regra)
ROTINA = {
    "Receituário Médico": ("Farmacia_Hospitalar", "R-RECEITA",
                           "receitas de rotina seguem para a farmácia"),
    "Guia de Solicitação de Procedimento": ("Auditoria_Autorizacoes", "R-GUIA",
                           "guias de rotina seguem para a auditoria de autorizações"),
}
REGRA_PRONTUARIO = ("R-PRONTUARIO", "laudos, altas e atestados de rotina seguem para o prontuário")
 
 
def decidir_destino(tipo: str, prioridade: str, requer_revisao: bool):
    """Devolve (destino, regra). A ORDEM importa: segurança, urgência, rotina."""
    if requer_revisao:
        return "Fila_Revisao_Humana", "R-REVISAO"
    if prioridade == "Urgente":
        return "Fila_Emergencia_Medica", "R-URGENCIA"
    if tipo in ROTINA:
        destino, regra, _ = ROTINA[tipo]
        return destino, regra
    return PADRAO, REGRA_PRONTUARIO[0]
 
 
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
    if regra == "R-REVISAO":
        detalhe = motivo or (
            f"falha na extração automática ({erro[:80]})"
            if erro
            else "; ".join(problemas or []) or f"baixa confiança na classificação ({score})"
        )
        return f"Enviado à revisão humana (regra R-REVISAO): {detalhe}."
    if regra == "R-URGENCIA":
        return (f"{tipo} com prioridade Urgente (achado crítico: {achado}); regra R-URGENCIA: "
                f"urgência tem precedência sobre a rota de rotina → {destino}.")
    descricao = ROTINA[tipo][2] if tipo in ROTINA else REGRA_PRONTUARIO[1]
    return (f"{tipo} com prioridade {prioridade} e confiança {score}; "
            f"regra {regra}: {descricao} → {destino}.")
 