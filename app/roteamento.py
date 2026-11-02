"""Regras de roteamento de documentos clínicos (H2.1.1).

Precedência estrita do edital: urgência → revisão → tipo.
Funções puras, determinísticas e sem chamadas a LLM.
"""

from collections.abc import Mapping
from typing import Any

from . import config
from .modelos.classificacao import TipoDocumento
from .modelos.destino import DecisaoRoteamento, Destino, Notificacao

PADRAO = Destino.PRONTUARIO_ELETRONICO

# tipo de documento -> (destino, id da regra, descrição da regra)
ROTINA = {
    TipoDocumento.RECEITUARIO_MEDICO.value: (
        Destino.FARMACIA_HOSPITALAR,
        "R-RECEITA",
        "receitas de rotina seguem para a farmácia",
    ),
    TipoDocumento.GUIA_PROCEDIMENTO.value: (
        Destino.AUDITORIA_AUTORIZACOES,
        "R-GUIA",
        "guias de rotina seguem para a auditoria de autorizações",
    ),
    "Guia": (
        Destino.AUDITORIA_AUTORIZACOES,
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


def decidir_destino(
    estado_ou_tipo: Mapping[str, Any] | str, *args, **kwargs
) -> Destino:
    """Função pura que devolve o destino aplicando estritamente a precedência:
    urgência → revisão → tipo (H2.1.1 T2).

    Retorna uma instância de Destino (que também é str).
    """
    (
        tipo,
        score,
        urgente,
        tem_pendencia,
        problemas,
        erro,
        _,
        _,
    ) = _extrair_atributos(estado_ou_tipo, *args, **kwargs)

    limite = float(kwargs.get("limite_confianca") or config.limiar_confianca())
    tipo_str = str(tipo) if tipo else ""

    # Precedência de Segurança: Revisão humana caso haja erro, pendência,
    # problemas de validação, score abaixo do limite ou tipo Desconhecido.
    if (
        tem_pendencia
        or bool(erro)
        or len(problemas) > 0
        or score < limite
        or tipo_str in ("Desconhecido", TipoDocumento.DESCONHECIDO.value)
    ):
        return Destino.FILA_REVISAO_HUMANA

    # Precedência de Urgência: casos críticos sem pendência vão imediatamente para a emergência
    if urgente:
        return Destino.FILA_EMERGENCIA_MEDICA

    # Precedência de Tipo: encaminhamento por tipo de documento clínico
    if tipo_str == TipoDocumento.RECEITUARIO_MEDICO.value:
        return Destino.FARMACIA_HOSPITALAR

    if tipo_str in (
        TipoDocumento.GUIA_PROCEDIMENTO.value,
        "Guia de Solicitação de Procedimento",
        "Guia de Solicitacao de Procedimento",
        "Guia",
        "guia",
    ):
        return Destino.AUDITORIA_AUTORIZACOES

    return Destino.PRONTUARIO_ELETRONICO


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
    tipo: str | None,
    prioridade: str | None,
    score: float,
    destino: Destino | str,
    regra: str,
    achado: str | None = None,
    problemas: list | None = None,
    erro: str | None = None,
) -> str:
    """Gera a justificativa textual explicativa da rota decidida."""
    destino_str = str(destino)
    if regra == "R-REVISAO" or destino_str == Destino.FILA_REVISAO_HUMANA.value:
        motivo = (
            f"falha na extração automática ({erro[:80]})"
            if erro
            else "; ".join(problemas or []) or f"score baixo ({score})"
        )
        return f"Enviado à revisão humana (regra R-REVISAO): {motivo}."

    if regra == "R-URGENCIA" or destino_str == Destino.FILA_EMERGENCIA_MEDICA.value:
        return (
            f"{tipo or 'Documento'} com prioridade Urgente (achado crítico: {achado or 'urgência clínica'}); "
            f"regra R-URGENCIA: urgência tem precedência sobre a rota de rotina → {destino_str}."
        )

    tipo_str = str(tipo) if tipo else ""
    descricao = ROTINA[tipo_str][2] if tipo_str in ROTINA else REGRA_PRONTUARIO[1]
    prio_str = prioridade or "Rotina"
    return (
        f"{tipo_str} com prioridade {prio_str} e confiança {score}; "
        f"regra {regra}: {descricao} → {destino_str}."
    )


gerar_justificativa = justificativa  # nome do card H2.2.1 T2

REGRA_PRONTUARIO = (
    "R-PRONTUARIO",
    "laudos, altas e atestados de rotina seguem para o prontuário",
)


def _extrair_atributos(
    estado_ou_tipo: Mapping[str, Any] | str,
    *args,
    **kwargs,
) -> tuple[str | None, float, bool, bool, list, str | None, str | None, str | None]:
    """Extrai (tipo, score, urgente, pendencia, problemas, erro, achado, paciente)
    seja de um dict de estado ou de argumentos posicionais/nomeados.
    """
    if isinstance(estado_ou_tipo, dict):
        s = estado_ou_tipo
        ext = s.get("extracao")
        cla = s.get("classificacao")

        # Tipo
        tipo = s.get("tipo") or s.get("tipo_documento")
        if not tipo and ext is not None:
            tipo = getattr(ext, "tipo_documento", None)
        if not tipo and cla is not None:
            tipo = getattr(cla, "tipo_documento", None)
        if hasattr(tipo, "value"):
            tipo = tipo.value

        # Score
        score = s.get("score")
        if score is None and cla is not None:
            score = getattr(cla, "score_confianca_classificacao", None)
        if score is None and ext is not None:
            score = getattr(ext, "score_confianca_classificacao", None)
        score = float(score) if score is not None else 1.0

        # Urgência
        urgente = False
        if (
            s.get("urgencia") is True
            or s.get("prioridade") in ("Urgente", "urgente")
            or s.get("nivel_prioridade") in ("Urgente", "urgente")
            or ext is not None
            and getattr(ext, "nivel_prioridade", None) == "Urgente"
            or cla is not None
            and getattr(cla, "nivel_prioridade", None) == "Urgente"
        ):
            urgente = True

        # Pendência / Revisão
        problemas = list(s.get("problemas") or [])
        erro = s.get("erro")
        pendencia_raw = s.get("pendencia") if "pendencia" in s else s.get("pendencias")

        tem_pendencia = False
        if s.get("requer_revisao") is True or bool(erro):
            tem_pendencia = True
        elif isinstance(pendencia_raw, bool):
            tem_pendencia = pendencia_raw
        elif isinstance(pendencia_raw, (list, tuple, str)) and bool(pendencia_raw):
            tem_pendencia = True
            if isinstance(pendencia_raw, list):
                problemas.extend(pendencia_raw)
            elif isinstance(pendencia_raw, str):
                problemas.append(pendencia_raw)
        elif len(problemas) > 0:
            tem_pendencia = True

        # Achado e paciente para mensagens
        achado = None
        paciente_nome = None
        if ext is not None:
            achado = getattr(ext, "diagnostico_principal", None) or tipo
            paciente = getattr(ext, "paciente", None)
            if paciente is not None:
                paciente_nome = getattr(paciente, "nome", None)
        achado = achado or tipo or "Achado crítico"

        return (
            tipo,
            score,
            urgente,
            tem_pendencia,
            problemas,
            erro,
            achado,
            paciente_nome,
        )

    # Argumentos posicionais / kwargs
    tipo = estado_ou_tipo
    if hasattr(tipo, "value"):
        tipo = tipo.value

    # Suporta assinatura clássica decidir_destino(tipo, prioridade, requer_revisao)
    if len(args) == 2 and isinstance(args[1], bool):
        prioridade_arg, requer_revisao_arg = args
        urgente = prioridade_arg == "Urgente"
        tem_pendencia = requer_revisao_arg
        score = kwargs.get("score", 1.0)
    else:
        score = args[0] if len(args) > 0 else kwargs.get("score", 1.0)
        urgente_arg = (
            args[1]
            if len(args) > 1
            else kwargs.get("urgencia", kwargs.get("urgente", False))
        )
        urgente = (urgente_arg is True) or (urgente_arg == "Urgente")
        pendencia_arg = (
            args[2]
            if len(args) > 2
            else kwargs.get("pendencia", kwargs.get("pendencias", False))
        )
        if isinstance(pendencia_arg, bool):
            tem_pendencia = pendencia_arg
        else:
            tem_pendencia = bool(pendencia_arg)

    problemas = list(kwargs.get("problemas") or [])
    erro = kwargs.get("erro")
    achado = kwargs.get("achado", tipo)
    paciente_nome = kwargs.get("paciente")

    return (
        tipo,
        float(score),
        urgente,
        tem_pendencia,
        problemas,
        erro,
        achado,
        paciente_nome,
    )


def criar_decisao_roteamento(
    estado_ou_tipo: Mapping[str, Any] | str,
    *args,
    **kwargs,
) -> DecisaoRoteamento:
    """Monta a DecisaoRoteamento completa (destino, auditoria, justificativa, notificacao)."""
    (
        tipo,
        score,
        urgente,
        _tem_pendencia,
        problemas,
        erro,
        achado,
        paciente_nome,
    ) = _extrair_atributos(estado_ou_tipo, *args, **kwargs)

    destino = decidir_destino(estado_ou_tipo, *args, **kwargs)

    if destino == Destino.FILA_EMERGENCIA_MEDICA:
        regra = "R-URGENCIA"
        requer_auditoria = False
        msg_paciente = f" paciente {paciente_nome}" if paciente_nome else ""
        notificacao = Notificacao(
            canal="Alerta_Plantao_Medico",
            mensagem=f"ALERTA URGENTE: {achado}{msg_paciente}.",
        )
    elif destino == Destino.FILA_REVISAO_HUMANA:
        regra = "R-REVISAO"
        requer_auditoria = True
        notificacao = None
        if urgente:
            notificacao = Notificacao(
                canal="Alerta_Plantao_Medico",
                mensagem="Possível urgência com dados ambíguos: revisar com prioridade.",
            )
    elif destino == Destino.FARMACIA_HOSPITALAR:
        regra = "R-RECEITA"
        requer_auditoria = False
        notificacao = None
    elif destino == Destino.AUDITORIA_AUTORIZACOES:
        regra = "R-GUIA"
        requer_auditoria = False
        notificacao = None
    else:
        regra = REGRA_PRONTUARIO[0]
        requer_auditoria = False
        notificacao = None

    prioridade_str = "Urgente" if urgente else "Rotina"
    just = justificativa(
        tipo=tipo,
        prioridade=prioridade_str,
        score=score,
        destino=destino,
        regra=regra,
        achado=achado,
        problemas=problemas,
        erro=erro,
    )

    return DecisaoRoteamento(
        destino_principal=destino,
        requer_auditoria_humana=requer_auditoria,
        justificativa_roteamento=just,
        regra_aplicada=regra,
        notificacao_gerada=notificacao,
    )
