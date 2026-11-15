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
    # H2.1.3 T1: laudos de exame, relatórios de alta e atestados -> Prontuario_Eletronico
    TipoDocumento.LAUDO_IMAGEM.value: (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    TipoDocumento.LAUDO_LABORATORIAL.value: (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    "Laudo de Exame": (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    "Laudo": (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    TipoDocumento.RELATORIO_ALTA.value: (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    "Relatório de Alta/Internação": (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    "Relatório de Internação": (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    "Relatorio de Alta": (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    "Alta": (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    TipoDocumento.ATESTADO_MEDICO.value: (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    "Atestado Medico": (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
    ),
    "Atestado": (
        Destino.PRONTUARIO_ELETRONICO,
        "R-PRONTUARIO",
        "laudos, altas e atestados de rotina seguem para o prontuário",
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
) -> Destino | str:
    """Função pura que devolve o destino aplicando estritamente a precedência:
    urgência → revisão → regras configuráveis → tipo (H2.1.1 T2 / H6.3.1 T3).

    Retorna uma instância de Destino ou str do destino configurado.
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
        cid,
    ) = _extrair_atributos(estado_ou_tipo, *args, **kwargs)

    limite = float(kwargs.get("limite_confianca") or config.limiar_confianca())
    tipo_str = str(tipo) if tipo else ""

    # Precedência de Segurança: Revisão humana caso haja erro, pendência,
    # problemas de validação, score abaixo do limite ou tipo Desconhecido / Não identificado.
    if (
        tem_pendencia
        or bool(erro)
        or len(problemas) > 0
        or score < limite
        or tipo_str
        in (
            "Desconhecido",
            TipoDocumento.DESCONHECIDO.value,
            "Não identificado",
            TipoDocumento.NAO_IDENTIFICADO.value,
        )
    ):
        return Destino.FILA_REVISAO_HUMANA

    # Precedência de Urgência: casos críticos sem pendência vão imediatamente para a emergência
    if urgente:
        return Destino.FILA_EMERGENCIA_MEDICA

    # H6.3.1 T3: Precedência de Regras Configuráveis (depois da urgência/revisão e antes do tipo)
    regras_custom = kwargs.get("regras_roteamento")
    if regras_custom is None and isinstance(estado_ou_tipo, dict):
        regras_custom = estado_ou_tipo.get("regras_roteamento")
    regra_cfg = avaliar_regras_configuraveis(tipo_str, cid, regras_custom)
    if regra_cfg is not None:
        return regra_cfg[0]

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

    # H2.1.3 T1: Laudo de Exame, Relatório de Alta/Internação e Atestado Médico -> Prontuario_Eletronico
    if tipo_str in (
        TipoDocumento.LAUDO_IMAGEM.value,
        TipoDocumento.LAUDO_LABORATORIAL.value,
        "Laudo de Exame de Imagem",
        "Laudo Laboratorial",
        "Laudo de Exame",
        "Laudo",
        "laudo",
    ):
        return Destino.PRONTUARIO_ELETRONICO

    if tipo_str in (
        TipoDocumento.RELATORIO_ALTA.value,
        "Relatório de Alta",
        "Relatorio de Alta",
        "Relatório de Alta/Internação",
        "Relatorio de Alta/Internacao",
        "Relatório de Internação",
        "Relatorio de Internacao",
        "Alta",
        "alta",
    ):
        return Destino.PRONTUARIO_ELETRONICO

    if tipo_str in (
        TipoDocumento.ATESTADO_MEDICO.value,
        "Atestado Médico",
        "Atestado Medico",
        "Atestado",
        "atestado",
    ):
        return Destino.PRONTUARIO_ELETRONICO

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
    descricao_custom: str | None = None,
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
    if descricao_custom:
        descricao = descricao_custom
    elif tipo_str in ROTINA:
        descricao = ROTINA[tipo_str][2]
    elif regra in REGRAS:
        descricao = REGRAS[regra]
    else:
        descricao = REGRA_PRONTUARIO[1]

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


def avaliar_regras_configuraveis(
    tipo: str | None,
    cid: str | None,
    regras_roteamento: list[Any] | None = None,
) -> tuple[str, str, str] | None:
    """H6.3.1 T3: avalia regras configuráveis do conjunto fechado (tipo igual / CID começa com).

    Retorna (destino, id_regra, descricao) ou None se nenhuma regra coincidir.
    """
    if regras_roteamento is None:
        try:
            from app.regras import servico_regras

            regras_roteamento = servico_regras().obter_regras().regras_roteamento
        except Exception:  # noqa: BLE001
            regras_roteamento = []

    if not regras_roteamento:
        return None

    tipo_str = str(tipo).strip() if tipo else ""
    cid_str = str(cid).strip().upper() if cid else ""

    for regra in regras_roteamento:
        if isinstance(regra, dict):
            r_id = regra.get("id") or "R-CONFIG"
            cond = regra.get("condicao") or {}
            if isinstance(cond, dict):
                c_tipo = str(cond.get("tipo", "")).strip().lower()
                c_valor = str(cond.get("valor", "")).strip()
            else:
                c_tipo = str(regra.get("tipo_condicao", "")).strip().lower()
                c_valor = str(regra.get("valor", "")).strip()
            r_destino = regra.get("destino")
            r_desc = regra.get("descricao")
        else:
            r_id = getattr(regra, "id", "R-CONFIG")
            cond = getattr(regra, "condicao", None)
            if hasattr(cond, "tipo"):
                c_tipo = getattr(cond.tipo, "value", str(cond.tipo)).strip().lower()
                c_valor = str(getattr(cond, "valor", "")).strip()
            elif isinstance(cond, dict):
                c_tipo = str(cond.get("tipo", "")).strip().lower()
                c_valor = str(cond.get("valor", "")).strip()
            else:
                c_tipo = str(getattr(regra, "tipo_condicao", "")).strip().lower()
                c_valor = str(getattr(regra, "valor", "")).strip()
            r_destino = getattr(regra, "destino", None)
            r_desc = getattr(regra, "descricao", None)

        if not r_destino:
            continue

        casou = False
        if c_tipo in (
            "tipo_documento_igual",
            "tipo_documento_igual_a",
            "tipo_documento",
        ):
            if tipo_str and (
                tipo_str.lower() == c_valor.lower()
                or tipo_str.lower().startswith(c_valor.lower())
            ):
                casou = True
        elif (
            c_tipo in ("cid_comeca_com", "cid_inicia_com", "cid_comeca", "cid")
            and cid_str
            and cid_str.startswith(c_valor.upper())
        ):
            casou = True

        if casou:
            desc = r_desc or f"regra configurada {r_id}: encaminhar para {r_destino}"
            return (str(r_destino), str(r_id), desc)

    return None


def _extrair_atributos(
    estado_ou_tipo: Mapping[str, Any] | str,
    *args,
    **kwargs,
) -> tuple[
    str | None,
    float,
    bool,
    bool,
    list,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    """Extrai (tipo, score, urgente, pendencia, problemas, erro, achado, paciente, cid)
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

        # CID
        cid = s.get("cid") or s.get("cid_sugerido")
        if not cid and ext is not None:
            cid = getattr(ext, "cid_sugerido", None) or getattr(ext, "cid", None)
        if not cid and isinstance(s.get("dados_extraidos"), dict):
            cid = s["dados_extraidos"].get("cid_sugerido") or s["dados_extraidos"].get(
                "cid"
            )
        if not cid and cla is not None:
            cid = getattr(cla, "cid_sugerido", None) or getattr(cla, "cid", None)

        return (
            tipo,
            score,
            urgente,
            tem_pendencia,
            problemas,
            erro,
            achado,
            paciente_nome,
            str(cid) if cid is not None else None,
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
        score = (
            args[0]
            if len(args) > 0
            else kwargs.get("score", kwargs.get("score_confianca_classificacao", 1.0))
        )
        urgente_arg = (
            args[1]
            if len(args) > 1
            else (
                kwargs.get("urgencia")
                if "urgencia" in kwargs
                else kwargs.get(
                    "urgente",
                    kwargs.get("prioridade", kwargs.get("nivel_prioridade", False)),
                )
            )
        )
        urgente = (urgente_arg is True) or (urgente_arg in ("Urgente", "urgente"))
        pendencia_arg = (
            args[2]
            if len(args) > 2
            else kwargs.get(
                "pendencia",
                kwargs.get(
                    "pendencias",
                    kwargs.get("requer_revisao", kwargs.get("revisao", False)),
                ),
            )
        )
        if isinstance(pendencia_arg, bool):
            tem_pendencia = pendencia_arg
        else:
            tem_pendencia = bool(pendencia_arg)

    problemas = list(kwargs.get("problemas") or [])
    erro = kwargs.get("erro")
    achado = kwargs.get("achado", tipo)
    paciente_nome = kwargs.get("paciente")
    cid = kwargs.get("cid") or kwargs.get("cid_sugerido")

    return (
        tipo,
        float(score),
        urgente,
        tem_pendencia,
        problemas,
        erro,
        achado,
        paciente_nome,
        str(cid) if cid is not None else None,
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
        cid,
    ) = _extrair_atributos(estado_ou_tipo, *args, **kwargs)

    destino = decidir_destino(estado_ou_tipo, *args, **kwargs)
    fora_das_categorias = str(tipo or "") in (
        "Não identificado",
        TipoDocumento.NAO_IDENTIFICADO.value,
    )
    if fora_das_categorias and "documento fora das categorias" not in problemas:
        problemas = ["documento fora das categorias", *problemas]

    regras_custom = kwargs.get("regras_roteamento")
    if regras_custom is None and isinstance(estado_ou_tipo, dict):
        regras_custom = estado_ou_tipo.get("regras_roteamento")
    regra_cfg = avaliar_regras_configuraveis(tipo, cid, regras_custom)
    desc_custom = None

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
        if urgente and not fora_das_categorias:
            notificacao = Notificacao(
                canal="Alerta_Plantao_Medico",
                mensagem="Possível urgência com dados ambíguos: revisar com prioridade.",
            )
    elif regra_cfg is not None and str(regra_cfg[0]) == str(destino):
        regra = regra_cfg[1]
        desc_custom = regra_cfg[2]
        requer_auditoria = False
        notificacao = None
    elif destino == Destino.FARMACIA_HOSPITALAR:
        regra = "R-RECEITA"
        requer_auditoria = False
        notificacao = None
    elif destino == Destino.AUDITORIA_AUTORIZACOES:
        regra = "R-GUIA"
        requer_auditoria = False
        notificacao = None
    elif destino == Destino.PRONTUARIO_ELETRONICO:
        regra = "R-PRONTUARIO"
        requer_auditoria = False
        notificacao = None
    else:
        regra = regra_cfg[1] if regra_cfg else REGRA_PRONTUARIO[0]
        desc_custom = regra_cfg[2] if regra_cfg else None
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
        descricao_custom=desc_custom,
    )

    return DecisaoRoteamento(
        destino_principal=destino,
        requer_auditoria_humana=requer_auditoria,
        justificativa_roteamento=just,
        regra_aplicada=regra,
        notificacao_gerada=notificacao,
    )
