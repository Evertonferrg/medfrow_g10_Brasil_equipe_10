import json
import logging
from datetime import date, datetime, timedelta, timezone

from pydantic import TypeAdapter, ValidationError

from app import storage
from app.eventos import servico_padrao
from app.schemas import ResultadoTriagem

logger = logging.getLogger(__name__)

PREFIXOS = ("processados/", "auditoria_humana/", "rejeitados/")

# Os eventos são gravados em UTC; o período é interpretado no horário de Brasília
# (UTC-3, sem horário de verão desde 2019).
FUSO = timezone(timedelta(hours=-3))

_adaptador = TypeAdapter(list[ResultadoTriagem])


class ExportacaoInvalida(Exception):
    """Falha de período, leitura ou formato: a exportação é interrompida."""


def _ler_json(caminho: str) -> dict:
    bruto = storage.ler(caminho)
    if bruto is None:
        raise ExportacaoInvalida(f"{caminho}: objeto listado mas não encontrado.")
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as e:
        raise ExportacaoInvalida(f"{caminho}: JSON corrompido ({e.msg}).") from e
    if not isinstance(dados, dict):
        raise ExportacaoInvalida(f"{caminho}: formato inesperado (não é um objeto).")
    return dados


def _chegada(documento_id) -> datetime | None:
    """Hora do 1º evento (recebido) do documento, ou None se não houver evento."""
    if not isinstance(documento_id, str):
        return None
    try:
        eventos = servico_padrao().listar(documento_id)
        return datetime.fromisoformat(eventos[0]["em"]) if eventos else None
    except (OSError, ValueError, KeyError):
        return None


def coletar(inicio: date, fim: date) -> list[dict]:
    achados: list[tuple[datetime, str, dict]] = []
    for prefixo in PREFIXOS:
        for caminho in storage.listar(prefixo):
            if not caminho.endswith(".json"):
                continue
            dados = _ler_json(caminho)
            chegada = _chegada(dados.get("documento_id"))
            if chegada is None:
                logger.warning(
                    "Histórico: %s ignorado (sem evento de chegada)", caminho
                )
                continue
            if inicio <= chegada.astimezone(FUSO).date() <= fim:
                achados.append((chegada, caminho, dados))
    achados.sort(key=lambda a: (a[0], a[1]))  # ordem cronológica, estável
    return [dados for _, _, dados in achados]


def exportar(inicio: date, fim: date) -> list[ResultadoTriagem]:
    if inicio > fim:
        raise ExportacaoInvalida(
            "A data de início deve ser anterior ou igual à de fim."
        )
    brutos = coletar(inicio, fim)
    try:
        return _adaptador.validate_python(brutos)  # valida a lista inteira
    except ValidationError as e:
        primeiro = e.errors()[0]
        local = ".".join(str(p) for p in primeiro["loc"])
        raise ExportacaoInvalida(
            f"Exportação interrompida: {e.error_count()} erro(s) de formato. "
            f"Primeiro: {local} — {primeiro['msg']}"
        ) from e


def serializar(resultados: list[ResultadoTriagem]) -> bytes:
    return _adaptador.dump_json(resultados, indent=2)
