"""H2.3.2 T2 / H5.3.1 — ServicoEventos: log de eventos por documento em eventos/<id>.json.

O status atual é o do último evento. Cada evento guarda o hash do anterior (cadeia):
`verificar_cadeia` acusa evento alterado ou removido do meio. Não detecta quem
recalcula a cadeia inteira nem o corte dos últimos eventos (não há assinatura nem
âncora externa). Não usar retenção do bucket: ela impediria mover objetos.
Guarda só id, status, horário, autor e, nas correções, o campo e os valores antes/depois.
"""

from __future__ import annotations

import functools
import hashlib
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
AUTORES = ("agente", "auditora")


def _hash_do_evento(evento: dict) -> str:
    corpo = {k: v for k, v in evento.items() if k != "hash"}
    texto = json.dumps(corpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class ServicoEventos:
    def __init__(
        self,
        pasta: Path | str = "eventos",
        relogio: Callable[[], datetime] | None = None,
    ):
        self._pasta = Path(
            pasta
        )  # a pasta é criada no 1º registro, não ao importar o app
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
        self,
        documento_id: str,
        status: StatusDocumento,
        detalhe: str | None = None,
        **extra,
    ) -> dict:
        caminho = self._caminho(documento_id)
        evento = {
            "status": StatusDocumento(status).value,
            "em": self._relogio().isoformat(),
        }
        if detalhe:
            evento["detalhe"] = detalhe
        nulos_ok = extra.get("campo") is not None
        evento.update(
            {
                k: v
                for k, v in extra.items()
                if v is not None or (nulos_ok and k in ("valor_anterior", "valor_novo"))
            }
        )
        with self._lock:
            self._pasta.mkdir(parents=True, exist_ok=True)
            eventos = self.listar(documento_id)
            evento["hash_anterior"] = eventos[-1].get("hash", "") if eventos else ""
            evento["hash"] = _hash_do_evento(evento)
            eventos.append(evento)
            tmp = caminho.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(eventos, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, caminho)  # escrita atômica
        return evento

    def registrar_falha_armazenamento(self, documento_id: str, detalhe: str):

        return self.registrar(
            documento_id,
            StatusDocumento.FALHA_OCI,
            detalhe=detalhe,
        )

    def registrar_decisao(
        self,
        documento_id: str,
        status: StatusDocumento,
        *,
        autor_tipo: str,
        autor_nome: str,
        regra_aplicada: str | None = None,
        campo: str | None = None,
        valor_anterior=None,
        valor_novo=None,
        detalhe: str | None = None,
    ) -> dict:
        """H5.3.1 T1/T2: decisão do agente (com a regra) ou da auditora (com nome e valores)."""
        if autor_tipo not in AUTORES:
            raise ValueError("autor_tipo deve ser 'agente' ou 'auditora'")
        return self.registrar(
            documento_id,
            status,
            detalhe,
            tipo="decisao",
            autor_tipo=autor_tipo,
            autor_nome=autor_nome,
            regra_aplicada=regra_aplicada,
            campo=campo,
            valor_anterior=valor_anterior,
            valor_novo=valor_novo,
        )

    def verificar_cadeia(self, documento_id: str) -> list[str]:
        """H5.3.1 T3: lista de problemas da cadeia (vazia = íntegra). Eventos antigos,
        sem hash, são aceitos só no começo da trilha."""
        problemas = []
        anterior = ""
        for i, ev in enumerate(self.listar(documento_id)):
            if "hash" not in ev:
                if anterior:
                    problemas.append(
                        f"evento {i}: sem hash depois de evento verificável"
                    )
                continue
            if ev.get("hash_anterior") != anterior:
                problemas.append(f"evento {i}: não encadeia com o anterior")
            if _hash_do_evento(ev) != ev["hash"]:
                problemas.append(f"evento {i}: conteúdo alterado")
            anterior = ev["hash"]
        return problemas

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
    """Decisão automática (H5.3.1): autor "agente", com a regra aplicada e o destino.

    Chamar em arquivar(), depois de salvar o resultado. Falha ao registrar o evento
    não derruba o processamento (o resultado já foi salvo).
    """
    decisao = resultado.decisao_roteamento
    destino = str(
        getattr(decisao.destino_principal, "value", decisao.destino_principal)
    )
    status = (
        StatusDocumento.EM_AUDITORIA_HUMANA
        if destino == "Fila_Revisao_Humana"
        else StatusDocumento.PROCESSADO
    )
    try:
        servico_padrao().registrar_decisao(
            documento_id,
            status,
            autor_tipo="agente",
            autor_nome="agente",
            regra_aplicada=getattr(decisao, "regra_aplicada", None),
            detalhe=f"destino: {destino}",
        )
    except (OSError, ValueError):
        logger.exception("Não foi possível registrar o evento de status")


def status_do_documento(documento_id: str, resultado: dict | None = None) -> str | None:
    """Status do ciclo de vida do documento (recebido, processando, processado,
    em_auditoria_humana ou rejeitado). Vem dos eventos; sem evento (documento antigo),
    é deduzido do resultado salvo. Devolve None se não houver nenhum dos dois."""
    try:
        atual = servico_padrao().status_atual(documento_id)
    except (OSError, ValueError):
        atual = None
    if atual:
        return atual.value
    if resultado:
        destino = (resultado.get("decisao_roteamento") or {}).get("destino_principal")
        if destino == "Fila_Revisao_Humana":
            return StatusDocumento.EM_AUDITORIA_HUMANA.value
        return StatusDocumento.PROCESSADO.value
    return None
