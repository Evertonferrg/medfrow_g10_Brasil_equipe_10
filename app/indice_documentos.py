from collections.abc import Iterable
from datetime import UTC, datetime
from threading import Lock

from pydantic import BaseModel


class ResumoDocumento(BaseModel):
    documento_id: str
    tipo_documento: str | None = None
    nivel_prioridade: str | None = None
    destino: str | None = None
    status: str = "Processado"
    data: datetime
    motivo_rejeicao: str | None = None
    canal_origem: str | None = None


def resumo_de_resultado(
    res: dict,
    canal_origem: str | None = None,
    status: str | None = None,
    data: datetime | None = None,
) -> ResumoDocumento:
    """Converte o resultado completo da triagem no resumo guardado no índice."""
    cl = res.get("classificacao") or {}
    d = res.get("decisao_roteamento") or {}
    # AJUSTAR: nomes reais dos campos de status, data e motivo no seu resultado
    return ResumoDocumento(
        documento_id=res["documento_id"],
        tipo_documento=cl.get("tipo_documento"),
        nivel_prioridade=cl.get("nivel_prioridade"),
        destino=d.get("destino_principal"),
        status=status or res.get("status_documento") or "Processado",
        data=data or res.get("data") or datetime.now(UTC),
        motivo_rejeicao=res.get("motivo_rejeicao"),
        canal_origem=canal_origem or res.get("canal_origem"),
    )


class IndiceDocumentos:
    """Resumo de cada documento em memória: listar não lê o OCI documento a documento."""

    def __init__(self) -> None:
        self._por_id: dict[str, ResumoDocumento] = {}
        self._lock = Lock()

    def reconstruir(self, resumos: Iterable[ResumoDocumento]) -> None:
        """Na inicialização: lê o bucket uma vez e monta o índice."""
        with self._lock:
            self._por_id = {r.documento_id: r for r in resumos}

    def atualizar(self, resumo: ResumoDocumento) -> None:
        """A cada gravação (resultado, mudança de status ou decisão de revisão)."""
        with self._lock:
            self._por_id[resumo.documento_id] = resumo

    def obter(self, documento_id: str) -> ResumoDocumento | None:
        with self._lock:
            return self._por_id.get(documento_id)

    def listar(self, canal_origem: str | None = None) -> list[ResumoDocumento]:
        with self._lock:
            itens = list(self._por_id.values())
        if canal_origem:
            itens = [r for r in itens if r.canal_origem == canal_origem]
        return sorted(
            itens, key=lambda r: r.data, reverse=True
        )  # mais recente primeiro


indice = IndiceDocumentos()
