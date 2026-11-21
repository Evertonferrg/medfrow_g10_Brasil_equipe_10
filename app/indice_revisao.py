"""H4.2.1 T1 — índice dos casos em revisão humana.

Os ids vêm dos eventos (último status = em_auditoria_humana) e o conteúdo vem do
resultado salvo em auditoria_humana/ (via resposta.carregar_resultado). Assim a fila
não depende de listar o storage e o caso sai dela quando a auditora decide (novo evento).

Expõe só o que a fila precisa; texto do documento e dados do paciente não saem daqui.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.eventos import ServicoEventos
from app.fila import CasoRevisao
from app.status import StatusDocumento

logger = logging.getLogger(__name__)


def _frase(texto) -> str:
    return " ".join(str(texto).split())


def _data(valor) -> datetime:
    try:
        data = datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return datetime.now(UTC)
    return data if data.tzinfo else data.replace(tzinfo=UTC)


def _motivos(resultado: dict) -> list[str]:
    motivos = []
    for m in resultado.get("problemas") or []:
        if isinstance(m, dict):
            m = m.get("motivo") or m.get("descricao") or m.get("mensagem")
        if m:
            motivos.append(_frase(m))
    if not motivos:  # sem problema listado: a justificativa do roteamento é o motivo
        decisao = resultado.get("decisao_roteamento") or {}
        if decisao.get("justificativa_roteamento"):
            motivos.append(_frase(decisao["justificativa_roteamento"]))
    return motivos


def caso_de_resultado(documento_id: str, resultado: dict, chegada: str) -> CasoRevisao:
    """`resultado`: ResultadoTriagem em dict (o que carregar_resultado devolve)."""
    classificacao = resultado.get("classificacao") or {}
    return CasoRevisao(
        documento_id=documento_id,
        tipo=classificacao.get("tipo_documento") or "Desconhecido",
        motivos=_motivos(resultado),
        chegada_em=_data(chegada),
        prioridade=classificacao.get("nivel_prioridade") or "Rotina",
    )


class IndiceRevisao:
    def __init__(self, eventos: ServicoEventos, carregar=None, indice_documentos=None):
        self._eventos = eventos
        self._carregar = carregar  # callable(documento_id) -> dict | None
        self._indice_documentos = indice_documentos

    def _carregar_resultado(self, documento_id: str):
        if self._carregar is None:
            from app.resposta import carregar_resultado  # padrão do projeto

            self._carregar = carregar_resultado
        return self._carregar(documento_id)

    def listar_casos_revisao(self) -> list[CasoRevisao]:
        casos = []
        vistos: set[str] = set()
        for documento_id, chegada in self._eventos.listar_por_status(
            StatusDocumento.EM_AUDITORIA_HUMANA
        ):
            vistos.add(documento_id)
            try:
                resultado = self._carregar_resultado(documento_id)
            except Exception:  # resultado fora do formato não derruba a fila
                logger.exception("Resultado ilegível na fila de revisão")
                continue
            if resultado:
                casos.append(caso_de_resultado(documento_id, resultado, chegada))

        if self._indice_documentos is not None:
            alvo = StatusDocumento.EM_AUDITORIA_HUMANA.value
            for resumo in self._indice_documentos.listar():
                doc_id = resumo.documento_id
                if doc_id in vistos or resumo.status != alvo:
                    continue
                try:
                    if self._eventos.listar(doc_id):
                        continue
                    resultado = self._carregar_resultado(doc_id)
                except Exception:
                    logger.exception("Resultado ilegível na fila de revisão")
                    continue
                if resultado:
                    chegada = (
                        resumo.data.isoformat()
                        if hasattr(resumo.data, "isoformat")
                        else str(resumo.data)
                    )
                    casos.append(caso_de_resultado(doc_id, resultado, chegada))
                    vistos.add(doc_id)

        return casos
