"""H2.3.2 T2 — ServicoEventos: log de eventos por documento em eventos/<id>.json.

O status atual é o do último evento. Base de H5.2.2 e H5.3.1.
Não guarda dados pessoais: só id, status, horário e um detalhe curto opcional.
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.status import StatusDocumento

_ID_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,100}$")  # bloqueia path traversal


class ServicoEventos:
    def __init__(
        self,
        pasta: Path | str = "eventos",
        relogio: Callable[[], datetime] | None = None,
    ):
        self._pasta = Path(pasta)
        self._pasta.mkdir(parents=True, exist_ok=True)
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
