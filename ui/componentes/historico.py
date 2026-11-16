"""H5.2.1 — funções puras da página Histórico (testáveis sem Streamlit)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.modelos.classificacao import TipoDocumento
from app.modelos.destino import Destino
from ui.componentes.fila import ROTULO_STATUS

FUSO = timezone(timedelta(hours=-3))  # horário de Brasília, o mesmo da API
MENSAGEM_VAZIO = "Nenhum documento encontrado."

TIPOS = [t.value for t in TipoDocumento]
PRIORIDADES = ["Urgente", "Rotina"]
DESTINOS = [d.value for d in Destino]
STATUS = list(ROTULO_STATUS)


def hoje() -> date:
    return datetime.now(FUSO).date()


def montar_params(
    inicio: date | None = None,
    fim: date | None = None,
    tipos=(),
    prioridades=(),
    destinos=(),
    status=(),
) -> list[tuple[str, str]]:
    """Parâmetros do GET /historico; filtro vazio não é enviado."""
    params: list[tuple[str, str]] = []
    if inicio:
        params.append(("data_inicio", inicio.isoformat()))
    if fim:
        params.append(("data_fim", fim.isoformat()))
    for nome, valores in (
        ("tipo", tipos),
        ("prioridade", prioridades),
        ("destino", destinos),
        ("status", status),
    ):
        params.extend((nome, v) for v in valores)
    return params


def linhas_tabela(itens: list[dict]) -> list[dict]:
    """Uma linha por documento, com os rótulos das colunas e a data em Brasília."""
    linhas = []
    for i in itens:
        chegada = datetime.fromisoformat(i["chegada_em"]).astimezone(FUSO)
        linhas.append(
            {
                "Documento": i["documento_id"],
                "Chegada": chegada.strftime("%d/%m/%Y %H:%M"),
                "Tipo": i.get("tipo") or "—",
                "Prioridade": i.get("prioridade") or "—",
                "Destino": i.get("destino") or "—",
                "Status": ROTULO_STATUS.get(i.get("status"), i.get("status") or "—"),
            }
        )
    return linhas
