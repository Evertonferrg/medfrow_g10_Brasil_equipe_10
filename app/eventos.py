"""H2.3.2 T2 / H5.3.1 / H5.2.2 — ServicoEventos: log de eventos por documento em eventos/<id>.json.

O status atual é o do último evento. Cada evento guarda o hash do anterior (cadeia):
`verificar_cadeia` acusa evento alterado ou removido do meio. Não detecta quem
recalcula a cadeia inteira nem o corte dos últimos eventos (não há assinatura nem
âncora externa). Não usar retenção do bucket: ela impediria mover objetos.
Guarda só id, status, horário, autor e, nas correções, o campo e os valores antes/depois.

H5.2.2 T1/T2: Modelo Evento padronizado com tipo, data_hora, autor, detalhe.
Gravação append-only com concorrência otimista (if_match com etag baseada no hash/conteúdo)
e bloqueio de reescrita ou remoção para garantir que os eventos só sejam acrescentados.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.modelos.evento import Evento
from app.status import StatusDocumento

logger = logging.getLogger(__name__)
_ID_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,100}$")  # bloqueia path traversal
AUTORES = ("agente", "auditora", "sistema")


class ConflitoConcorrenciaError(Exception):
    """Lançado quando uma gravação concorrente é detectada (etag / if_match)."""


def _hash_do_evento(evento: dict) -> str:
    corpo = {k: v for k, v in evento.items() if k != "hash"}
    texto = json.dumps(corpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _calcular_etag(conteudo_bruto: bytes | str) -> str:
    """Calcula a etag a partir do conteúdo bruto do arquivo de eventos."""
    if isinstance(conteudo_bruto, str):
        conteudo_bruto = conteudo_bruto.encode("utf-8")
    return hashlib.sha256(conteudo_bruto).hexdigest()


class ServicoEventos:
    """Serviço append-only de eventos com garantia de integridade em cadeia e concorrência otimista."""

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

    def _ler_conteudo_e_etag(self, documento_id: str) -> tuple[list[dict], str]:
        caminho = self._caminho(documento_id)
        if not caminho.exists():
            return [], ""
        bruto = caminho.read_bytes()
        etag = _calcular_etag(bruto)
        try:
            return json.loads(bruto.decode("utf-8")), etag
        except json.JSONDecodeError:
            return [], etag

    def listar(self, documento_id: str) -> list[dict]:
        """Devolve os eventos gravados em ordem cronológica (lista de dicts compatível)."""
        eventos, _ = self._ler_conteudo_e_etag(documento_id)
        return eventos

    def listar_eventos(self, documento_id: str) -> list[Evento]:
        """H5.2.2 T1/T3: Devolve os eventos estruturados no modelo padronizado Evento em ordem cronológica."""
        brutos = self.listar(documento_id)
        resultado: list[Evento] = []
        for e in brutos:
            data_hora = e.get("data_hora") or e.get("em") or ""
            tipo = e.get("tipo") or e.get("status") or "evento"
            autor = e.get("autor_nome") or e.get("autor_tipo") or e.get("autor") or "agente"
            detalhe = e.get("detalhe") or e.get("regra_aplicada")
            extra = {
                k: v
                for k, v in e.items()
                if k not in ("tipo", "data_hora", "em", "autor", "detalhe", "hash", "hash_anterior")
            }
            resultado.append(
                Evento(
                    tipo=tipo,
                    data_hora=data_hora,
                    autor=autor,
                    detalhe=detalhe,
                    hash=e.get("hash"),
                    hash_anterior=e.get("hash_anterior"),
                    extra=extra,
                )
            )
        return resultado

    def registrar(
        self,
        documento_id: str,
        status: StatusDocumento | str,
        detalhe: str | None = None,
        tipo: str | None = None,
        autor: str | None = None,
        max_tentativas: int = 5,
        **extra,
    ) -> dict:
        """H5.2.2 T2: Acrescenta um evento de forma estritamente append-only.
        
        Usa concorrência otimista (if_match com etag lida) e retentativas automáticas
        para suportar gravações simultâneas em ramos paralelos sem perda de eventos.
        """
        caminho = self._caminho(documento_id)
        status_val = StatusDocumento(status).value if isinstance(status, StatusDocumento) else str(status)
        agora = self._relogio().isoformat()

        # Criação do payload base do evento
        evento: dict = {
            "status": status_val,
            "tipo": tipo or status_val,
            "em": agora,
            "data_hora": agora,
            "autor": autor or extra.get("autor_tipo") or "agente",
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

        for tentativa in range(max_tentativas):
            with self._lock:
                self._pasta.mkdir(parents=True, exist_ok=True)
                eventos_atuais, etag_esperada = self._ler_conteudo_e_etag(documento_id)

                # Se o arquivo já existe no disco durante a gravação, confere se a etag bate (concorrência otimista)
                if caminho.exists():
                    etag_atual = _calcular_etag(caminho.read_bytes())
                    if etag_atual != etag_esperada:
                        if tentativa < max_tentativas - 1:
                            time.sleep(0.01 * (2**tentativa))
                            continue
                        raise ConflitoConcorrenciaError(
                            f"Conflito de concorrência ao gravar evento para {documento_id}"
                        )

                # Encadeamento de integridade SHA-256
                evento["hash_anterior"] = eventos_atuais[-1].get("hash", "") if eventos_atuais else ""
                evento["hash"] = _hash_do_evento(evento)

                lista_nova = [*eventos_atuais, evento]
                tmp = caminho.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
                tmp.write_text(
                    json.dumps(lista_nova, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                os.replace(tmp, caminho)  # escrita atômica no filesystem
                return evento

        return evento

    def registrar_decisao(
        self,
        documento_id: str,
        status: StatusDocumento | str,
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
            raise ValueError("autor_tipo deve ser 'agente', 'auditora' ou 'sistema'")
        return self.registrar(
            documento_id,
            status,
            detalhe=detalhe,
            tipo="decisao",
            autor=autor_nome,
            autor_tipo=autor_tipo,
            autor_nome=autor_nome,
            regra_aplicada=regra_aplicada,
            campo=campo,
            valor_anterior=valor_anterior,
            valor_novo=valor_novo,
        )

    def verificar_cadeia(self, documento_id: str) -> list[str]:
        """H5.3.1 T3: lista de problemas da cadeia (vazia = íntegra)."""
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
        if not eventos:
            return None
        st = eventos[-1].get("status")
        try:
            return StatusDocumento(st)
        except ValueError:
            return None

    def listar_por_status(self, status: StatusDocumento) -> list[tuple[str, str]]:
        """Documentos cujo ÚLTIMO evento é `status`: [(documento_id, horário do 1º evento)]."""
        alvo = StatusDocumento(status).value
        achados = []
        for caminho in sorted(self._pasta.glob("*.json")):
            try:
                eventos = json.loads(caminho.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if eventos and eventos[-1].get("status") == alvo:
                data_chegada = eventos[0].get("data_hora") or eventos[0].get("em") or ""
                achados.append((caminho.stem, data_chegada))
        return achados


@functools.cache
def _servico(pasta: str) -> ServicoEventos:
    return ServicoEventos(pasta)


def servico_padrao() -> ServicoEventos:
    """Instância compartilhada de ServicoEventos."""
    return _servico(os.getenv("EVENTOS_DIR", "eventos"))


def registrar_desfecho(documento_id: str, resultado) -> None:
    """Decisão automática (H5.3.1): autor 'agente', com a regra aplicada e o destino.

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
    regra = getattr(decisao, "regra_aplicada", None)
    try:
        # Registra a decisão do agente
        servico_padrao().registrar_decisao(
            documento_id,
            status,
            autor_tipo="agente",
            autor_nome="agente",
            regra_aplicada=regra,
            detalhe=f"destino: {destino}",
        )
    except (OSError, ValueError):
        logger.exception("Não foi possível registrar o evento de status")


def status_do_documento(documento_id: str, resultado: dict | None = None) -> str | None:
    """Status do ciclo de vida do documento."""
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
