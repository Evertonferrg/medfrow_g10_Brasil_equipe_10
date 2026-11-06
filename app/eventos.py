"""H2.3.2 T2 — ServicoEventos: log de eventos por documento em eventos/<id>.json.

O status atual é o do último evento. Base de H5.2.2 e H5.3.1.
Não guarda dados pessoais: só id, status, horário e um detalhe curto opcional.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.status import StatusDocumento

logger = logging.getLogger(__name__)
_ID_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,100}$")  # bloqueia path traversal


class ServicoEventos:
    def __init__(
        self,
        pasta: Path | str = "eventos",
        relogio: Callable[[], datetime] | None = None,
    ):
        self._pasta = Path(pasta)  # a pasta é criada no 1º registro, não ao importar o app
        self._relogio = relogio or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()

    def _caminho(self, documento_id: str) -> Path:
        if not _ID_VALIDO.match(documento_id or ""):
            raise ValueError("documento_id inválido")
        return self._pasta / f"{documento_id}.json"

    def listar(self, documento_id: str) -> list[dict]:
        caminho = self._caminho(documento_id)
        if not caminho.exists():
            return []
        return json.loads(caminho.read_text(encoding="utf-8"))

    def registrar(
        self, documento_id: str, status: StatusDocumento, detalhe: str | None = None
    ) -> dict:
        caminho = self._caminho(documento_id)
        evento = {
            "status": StatusDocumento(status).value,
            "em": self._relogio().isoformat(),
        }
        if detalhe:
            evento["detalhe"] = detalhe
        with self._lock:
            self._pasta.mkdir(parents=True, exist_ok=True)
            eventos = self.listar(documento_id)
            eventos.append(evento)
            tmp = caminho.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(eventos, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, caminho)  # escrita atômica
        return evento

    def status_atual(self, documento_id: str) -> StatusDocumento | None:
        eventos = self.listar(documento_id)
        return StatusDocumento(eventos[-1]["status"]) if eventos else None

    def listar_por_status(self, status: StatusDocumento) -> list[tuple[str, str]]:
        """Documentos cujo ÚLTIMO evento é `status`: [(documento_id, horário do 1º evento)].

        O 1º evento (recebido) é a chegada do documento; serve de horário de chegada na fila.
        """
        alvo = StatusDocumento(status).value
        achados = []
        for caminho in sorted(self._pasta.glob("*.json")):
            try:
                eventos = json.loads(caminho.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # arquivo ilegível não derruba a listagem
            if eventos and eventos[-1].get("status") == alvo:
                achados.append((caminho.stem, eventos[0]["em"]))
        return achados


@functools.cache
def _servico(pasta: str) -> ServicoEventos:
    return ServicoEventos(pasta)


def servico_padrao() -> ServicoEventos:
    """Instância compartilhada (main.py, resposta.py e a fila usam a mesma pasta)."""
    return _servico(os.getenv("EVENTOS_DIR", "eventos"))


def registrar_desfecho(documento_id: str, resultado) -> None:
    """Chamar em arquivar(), depois de salvar o resultado: revisão humana ou processado.

    Falha ao registrar o evento não derruba o processamento (o resultado já foi salvo).
    """
    destino = resultado.decisao_roteamento.destino_principal
    destino = str(getattr(destino, "value", destino))
    status = (
        StatusDocumento.EM_AUDITORIA_HUMANA
        if destino == "Fila_Revisao_Humana"
        else StatusDocumento.PROCESSADO
    )
    try:
        servico_padrao().registrar(documento_id, status)
    except (OSError, ValueError):
        logger.exception("Não foi possível registrar o evento de status")