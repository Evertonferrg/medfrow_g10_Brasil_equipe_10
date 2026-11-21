import json
import logging
from collections.abc import Collection
from datetime import UTC, date, datetime, timedelta, timezone

from pydantic import TypeAdapter, ValidationError

from app import storage
from app.eventos import servico_padrao, status_do_documento
from app.schemas import ResultadoTriagem
from app.status import StatusDocumento

logger = logging.getLogger(__name__)

PREFIXOS = ("processados/", "auditoria_humana/", "rejeitados/")
SUFIXO_ESTADO = ".estado.json"  # estado auxiliar da revisão (H4.4.1): não é triagem

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
    except UnicodeDecodeError as e:
        raise ExportacaoInvalida(
            f"{caminho}: arquivo com codificação inválida (UTF-8)."
        ) from e
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
            if not caminho.endswith(".json") or caminho.endswith(SUFIXO_ESTADO):
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


# ---------- H5.2.1: consulta com filtros ----------


def _eventos(documento_id) -> list[dict]:
    if not isinstance(documento_id, str):
        return []
    try:
        return servico_padrao().listar(documento_id)
    except (OSError, ValueError):
        return []


def _triagens_gravadas():
    """(caminho, dados, data_objeto) de cada triagem salva. Registro ilegível é
    pulado e logado: uma consulta não deve cair por causa de um arquivo ruim
    (a exportação, sim)."""
    for prefixo in PREFIXOS:
        for caminho, data_objeto in storage.listar_com_datas(prefixo):
            if not caminho.endswith(".json") or caminho.endswith(SUFIXO_ESTADO):
                continue
            try:
                yield caminho, _ler_json(caminho), data_objeto
            except ExportacaoInvalida:
                logger.warning("Histórico: %s ignorado (ilegível)", caminho)


def _chegada_e_status(
    caminho: str,
    dados: dict,
    data_objeto: datetime | None,
) -> tuple[datetime, str | None] | None:
    """Usa os eventos locais quando existirem; sem evento local (ex.: container
    novo lendo Bucket OCI), usa a data do objeto no storage e deduz o status."""
    doc_id = dados.get("documento_id")
    if not isinstance(doc_id, str) or not doc_id:
        return None

    eventos = _eventos(doc_id)
    if eventos:
        try:
            chegada = datetime.fromisoformat(eventos[0]["em"])
        except (KeyError, ValueError, TypeError):
            chegada = None
        if chegada is not None:
            if chegada.tzinfo is None:
                chegada = chegada.replace(tzinfo=UTC)
            return chegada, eventos[-1].get("status")

    # Fallback sem evento local: exige estrutura mínima de triagem válida.
    if data_objeto is None or not isinstance(dados.get("decisao_roteamento"), dict):
        return None
    if data_objeto.tzinfo is None:
        data_objeto = data_objeto.replace(tzinfo=UTC)
    if (
        caminho.startswith("rejeitados/")
        or str(dados.get("status", "")).lower() == "rejeitado"
    ):
        status = StatusDocumento.REJEITADO.value
    else:
        status = status_do_documento(doc_id, dados)
    return data_objeto, status


def _resumo(chegada: datetime, status: str | None, dados: dict) -> dict:
    classificacao = dados.get("classificacao") or {}
    decisao = dados.get("decisao_roteamento") or {}
    return {
        "documento_id": dados.get("documento_id"),
        "chegada_em": chegada.isoformat(),
        "tipo": classificacao.get("tipo_documento"),
        "prioridade": classificacao.get("nivel_prioridade"),
        "destino": decisao.get("destino_principal"),
        "status": status,
    }


def _passa(valor, aceitos: Collection[str]) -> bool:
    return not aceitos or valor in aceitos  # filtro vazio = não filtra


def consultar(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tipos: Collection[str] = (),
    prioridades: Collection[str] = (),
    destinos: Collection[str] = (),
    status: Collection[str] = (),
) -> list[dict]:
    """Triagens que atendem a TODOS os filtros informados (E entre filtros, OU entre
    os valores de um mesmo filtro). Datas inclusivas, no horário de Brasília.
    Mais recentes primeiro. Documento sem evento de chegada fica de fora (como na
    exportação). Lista vazia = nenhum documento encontrado."""
    if data_inicio and data_fim and data_inicio > data_fim:
        raise ExportacaoInvalida(
            "A data de início deve ser anterior ou igual à de fim."
        )
    achados = []
    for caminho, dados, data_objeto in _triagens_gravadas():
        meta = _chegada_e_status(caminho, dados, data_objeto)
        if meta is None:
            continue
        chegada, status_doc = meta
        dia = chegada.astimezone(FUSO).date()
        if (data_inicio and dia < data_inicio) or (data_fim and dia > data_fim):
            continue
        resumo = _resumo(chegada, status_doc, dados)
        if (
            _passa(resumo["tipo"], tipos)
            and _passa(resumo["prioridade"], prioridades)
            and _passa(resumo["destino"], destinos)
            and _passa(resumo["status"], status)
        ):
            achados.append(resumo)
    achados.sort(key=lambda r: (r["chegada_em"], r["documento_id"]), reverse=True)
    return achados
