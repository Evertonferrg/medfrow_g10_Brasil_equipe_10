"""H5.2.1 — GET /historico com filtros combináveis."""

import os
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import config, storage
from app.api.main import criar_app
from app.eventos import ServicoEventos
from app.status import StatusDocumento

HOJE = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)  # 12h em Brasília
ONTEM = HOJE - timedelta(days=1)
DIA = "2026-11-11"
DIA_ANTERIOR = "2026-11-10"
RECEITA = "Receituário Médico"
LAUDO = "Laudo de Exame de Imagem"
EMERGENCIA = "Fila_Emergencia_Medica"
FARMACIA = "Farmacia_Hospitalar"
REVISAO = "Fila_Revisao_Humana"


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)
    monkeypatch.setattr(config, "pasta_local", lambda: str(tmp_path / "storage"))
    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path / "eventos"))


@pytest.fixture
def client():
    return TestClient(criar_app(extrator=lambda *a, **k: {}))


def _doc(
    documento_id,
    *,
    tipo=RECEITA,
    prioridade="Rotina",
    destino=FARMACIA,
    status=StatusDocumento.PROCESSADO,
    chegada=HOJE,
    pasta="processados/rotina",
):
    storage.salvar(
        f"{pasta}/{documento_id}.json",
        {
            "status": "processado",
            "documento_id": documento_id,
            "classificacao": {
                "tipo_documento": tipo,
                "especialidade": None,
                "nivel_prioridade": prioridade,
                "score_confianca_classificacao": 0.9,
            },
            "problemas": [],
            "decisao_roteamento": {
                "destino_principal": destino,
                "requer_auditoria_humana": destino == REVISAO,
                "justificativa_roteamento": "teste",
                "regra_aplicada": "R-TESTE",
                "notificacao_gerada": None,
            },
        },
    )
    eventos = ServicoEventos(os.environ["EVENTOS_DIR"], relogio=lambda: chegada)
    eventos.registrar(documento_id, StatusDocumento.RECEBIDO)
    eventos.registrar(documento_id, status)


def _ids(resposta):
    assert resposta.status_code == 200
    return {r["documento_id"] for r in resposta.json()}


def _cenario():
    _doc("doc-urg-hoje", prioridade="Urgente", destino=EMERGENCIA, tipo=LAUDO)
    _doc("doc-urg-ontem", prioridade="Urgente", destino=EMERGENCIA, chegada=ONTEM)
    _doc("doc-rot-hoje")
    _doc(
        "doc-rev-hoje",
        destino=REVISAO,
        status=StatusDocumento.EM_AUDITORIA_HUMANA,
        pasta="auditoria_humana",
    )


def test_urgentes_de_hoje_devolve_so_os_urgentes_do_dia(client):
    _cenario()
    r = client.get(
        "/historico",
        params={"data_inicio": DIA, "data_fim": DIA, "prioridade": "Urgente"},
    )
    assert _ids(r) == {"doc-urg-hoje"}


def test_resumo_traz_os_campos_da_listagem(client):
    _doc("doc-urg-hoje", prioridade="Urgente", destino=EMERGENCIA, tipo=LAUDO)
    (item,) = client.get("/historico").json()
    assert item == {
        "documento_id": "doc-urg-hoje",
        "chegada_em": HOJE.isoformat(),
        "tipo": LAUDO,
        "prioridade": "Urgente",
        "destino": EMERGENCIA,
        "status": "processado",
    }


def test_sem_filtros_devolve_tudo_do_mais_recente_ao_mais_antigo(client):
    _cenario()
    ids = [r["documento_id"] for r in client.get("/historico").json()]
    assert ids[-1] == "doc-urg-ontem" and len(ids) == 4


def test_dois_filtros_combinados_restringem_o_resultado(client):
    _cenario()
    so_urgentes = _ids(client.get("/historico", params={"prioridade": "Urgente"}))
    assert so_urgentes == {"doc-urg-hoje", "doc-urg-ontem"}
    combinado = client.get(
        "/historico", params={"prioridade": "Urgente", "tipo": LAUDO}
    )
    assert _ids(combinado) == {"doc-urg-hoje"}


def test_varios_valores_do_mesmo_filtro_sao_alternativas(client):
    _cenario()
    r = client.get("/historico", params={"destino": [EMERGENCIA, REVISAO]})
    assert _ids(r) == {"doc-urg-hoje", "doc-urg-ontem", "doc-rev-hoje"}


def test_filtra_por_status(client):
    _cenario()
    r = client.get("/historico", params={"status": "em_auditoria_humana"})
    assert _ids(r) == {"doc-rev-hoje"}


def test_intervalo_de_datas_e_inclusivo(client):
    _cenario()
    r = client.get(
        "/historico", params={"data_inicio": DIA_ANTERIOR, "data_fim": DIA_ANTERIOR}
    )
    assert _ids(r) == {"doc-urg-ontem"}
    assert (
        len(client.get("/historico", params={"data_inicio": DIA_ANTERIOR}).json()) == 4
    )


def test_data_usa_o_horario_de_brasilia(client):
    # 01h UTC de 12/11 = 22h de 11/11 em Brasília
    _doc("doc-noite", chegada=datetime(2026, 11, 12, 1, 0, tzinfo=UTC))
    r = client.get("/historico", params={"data_inicio": DIA, "data_fim": DIA})
    assert _ids(r) == {"doc-noite"}


def test_filtro_sem_resultados_devolve_lista_vazia(client):
    _cenario()
    r = client.get("/historico", params={"tipo": "Atestado Médico"})
    assert r.status_code == 200 and r.json() == []


def test_historico_vazio_devolve_lista_vazia(client):
    assert client.get("/historico").json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"prioridade": "Qualquer"},
        {"tipo": "Inventado"},
        {"destino": "Lugar_Nenhum"},
        {"status": "sumido"},
        {"data_inicio": "ontem"},
        {"data_inicio": "2026-11-11", "data_fim": "2026-11-01"},
    ],
)
def test_filtro_invalido_devolve_422(client, params):
    assert client.get("/historico", params=params).status_code == 422


def test_ignora_registro_corrompido_e_arquivo_de_estado(client):
    _doc("doc-ok")
    storage.salvar("processados/rotina/doc-ruim.json", {"documento_id": "doc-ruim"})
    storage.salvar("auditoria_humana/doc-ok.estado.json", {"extracao": {}})
    caminho = storage._local("processados/rotina/quebrado.json")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("{ não é json")
    assert _ids(client.get("/historico")) == {"doc-ok"}


def test_um_dia_de_documentos_responde_em_menos_de_5s(client):
    for i in range(300):
        _doc(f"doc-vol-{i:04d}", prioridade="Urgente" if i % 3 == 0 else "Rotina")
    inicio = time.perf_counter()
    r = client.get(
        "/historico",
        params={"data_inicio": DIA, "data_fim": DIA, "prioridade": "Urgente"},
    )
    assert time.perf_counter() - inicio < 5
    assert len(r.json()) == 100


# ---------- página (funções puras da UI) ----------


def test_montar_params_so_envia_filtros_preenchidos():
    from datetime import date

    from ui.componentes.historico import montar_params

    assert montar_params() == []
    assert montar_params(
        date(2026, 11, 11),
        date(2026, 11, 11),
        prioridades=["Urgente"],
        tipos=["A", "B"],
    ) == [
        ("data_inicio", "2026-11-11"),
        ("data_fim", "2026-11-11"),
        ("tipo", "A"),
        ("tipo", "B"),
        ("prioridade", "Urgente"),
    ]


def test_linhas_da_tabela_usam_rotulos_e_horario_de_brasilia():
    from ui.componentes.historico import MENSAGEM_VAZIO, linhas_tabela

    (linha,) = linhas_tabela(
        [
            {
                "documento_id": "doc-1",
                "chegada_em": HOJE.isoformat(),
                "tipo": None,
                "prioridade": "Urgente",
                "destino": EMERGENCIA,
                "status": "em_auditoria_humana",
            }
        ]
    )
    assert linha["Chegada"] == "11/11/2026 12:00"
    assert linha["Tipo"] == "—" and linha["Status"] == "Em auditoria humana"
    assert MENSAGEM_VAZIO.lower().startswith("nenhum documento encontrado")
