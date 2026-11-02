"""H3.3.1: alerta ao plantão por MODELO DE TEXTO (sem LLM).

O submodelo de notificação já existe em app/schemas.py (`Notificacao`, usado por
`DecisaoRoteamento.notificacao_gerada`); aqui só montamos a mensagem.
"""
from typing import Optional

from .schemas import Notificacao

CANAL_PLANTAO = "Alerta_Plantao_Medico"
LIMITE_MENSAGEM = 200

NotificacaoGerada = Notificacao   # nome usado no card H3.3.1 T1


def _origem_legivel(canal_origem: Optional[str]) -> str:
    # "Pronto_Socorro" -> "Pronto-Socorro"
    return (canal_origem or "").strip().replace("_", "-")


def _cortar(texto: str, limite: int = LIMITE_MENSAGEM) -> str:
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def montar_mensagem_alerta(achado: Optional[str], paciente: Optional[str],
                           canal_origem: Optional[str]) -> str:
    """'ALERTA URGENTE: <achado> para paciente <nome> no <origem>.' (até 200 caracteres)."""
    achado = (achado or "").strip() or "achado crítico"
    paciente = (paciente or "").strip() or "não identificado"
    origem = _origem_legivel(canal_origem)
    msg = f"ALERTA URGENTE: {achado} para paciente {paciente}"
    if origem:
        msg += f" no {origem}"
    return _cortar(msg + ".")


def gerar_alerta(achado, paciente, canal_origem) -> Notificacao:
    return Notificacao(canal=CANAL_PLANTAO,
                       mensagem=montar_mensagem_alerta(achado, paciente, canal_origem))