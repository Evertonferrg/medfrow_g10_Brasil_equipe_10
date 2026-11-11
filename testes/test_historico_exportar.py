import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app import config, storage
from app.api.main import criar_app
from app.eventos import ServicoEventos
from app.schemas import ResultadoTriagem
from app.status import StatusDocumento

CHEGADA = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)  # 12h em Brasília
DIA = "2026-11-11"


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    """Sem OCI e sem tocar nas pastas reais: storage e eventos vão para tmp_path."""
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)
    monkeypatch.setattr(config, "pasta_local", lambda: str(tmp_path / "storage"))
    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path / "eventos"))


@pytest.fixture
def client():
    return TestClient(criar_app(extrator=lambda *a, **k: {}))


def _resultado(documento_id: str) -> dict:
    return {
        "status": "processado",
        "documento_id": documento_id,
        "problemas": [],
        "decisao_roteamento": {
            "destino_principal": "Fila_Revisao_Humana",
            "requer_auditoria_humana": True,
            "justificativa_roteamento": "teste",
            "regra_aplicada": "R-REVISAO",
            "notificacao_gerada": None,
        },
    }


def _triagem(prefixo, documento_id, chegada=CHEGADA, dados=None):
    """Grava o resultado no storage e o evento de chegada na pasta de eventos."""
    storage.salvar(f"{prefixo}/{documento_id}.json", dados or _resultado(documento_id))
    ServicoEventos(os.environ["EVENTOS_DIR"], relogio=lambda: chegada).registrar(
        documento_id, StatusDocumento.RECEBIDO
    )


def _exporta(client, inicio=DIA, fim=DIA):
    return client.get("/historico/exportar", params={"inicio": inicio, "fim": fim})


def test_periodo_com_3_triagens_exporta_as_3(client):
    _triagem("processados", "doc-hist-a")
    _triagem("auditoria_humana", "doc-hist-b")
    _triagem("rejeitados", "doc-hist-c")
    r = _exporta(client)
    assert r.status_code == 200
    assert {t["documento_id"] for t in r.json()} == {
        "doc-hist-a",
        "doc-hist-b",
        "doc-hist-c",
    }


def test_ignora_triagens_fora_do_periodo(client):
    _triagem("processados", "doc-hist-a")
    _triagem(
        "processados", "doc-hist-velho", chegada=datetime(2020, 1, 1, 12, tzinfo=UTC)
    )
    assert [t["documento_id"] for t in _exporta(client).json()] == ["doc-hist-a"]


def test_periodo_usa_o_horario_de_brasilia(client):
    # 01h UTC de 12/11 = 22h de 11/11 em Brasília
    _triagem(
        "processados",
        "doc-hist-noite",
        chegada=datetime(2026, 11, 12, 1, 0, tzinfo=UTC),
    )
    assert len(_exporta(client, "2026-11-11", "2026-11-11").json()) == 1
    assert _exporta(client, "2026-11-12", "2026-11-12").json() == []


def test_arquivo_exportado_passa_na_validacao(client):
    _triagem("processados", "doc-hist-a")
    TypeAdapter(list[ResultadoTriagem]).validate_json(_exporta(client).content)


def test_periodo_vazio_exporta_lista_vazia_valida(client):
    r = _exporta(client)
    assert r.status_code == 200
    assert r.json() == []
    TypeAdapter(list[ResultadoTriagem]).validate_json(r.content)


def test_documento_sem_evento_de_chegada_fica_fora_da_exportacao(client):
    storage.salvar("processados/doc-hist-antigo.json", _resultado("doc-hist-antigo"))
    assert _exporta(client).json() == []


def test_registro_invalido_interrompe_com_mensagem_clara(client):
    _triagem("processados", "doc-hist-ruim", dados={"documento_id": "doc-hist-ruim"})
    r = _exporta(client)
    assert r.status_code == 422
    assert "Exportação interrompida" in r.json()["detail"]


def test_inicio_maior_que_fim_retorna_422(client):
    assert _exporta(client, "2026-11-10", "2026-11-01").status_code == 422
