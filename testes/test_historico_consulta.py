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


def test_documento_no_bucket_oci_sem_evento_local_aparece_no_historico(
    client, monkeypatch
):
    import json
    from types import SimpleNamespace

    objetos = {
        "processados/rotina/doc-oci-rot.json": (
            HOJE,
            {
                "status": "processado",
                "documento_id": "doc-oci-rot",
                "classificacao": {
                    "tipo_documento": RECEITA,
                    "especialidade": None,
                    "nivel_prioridade": "Rotina",
                    "score_confianca_classificacao": 0.92,
                },
                "problemas": [],
                "decisao_roteamento": {
                    "destino_principal": FARMACIA,
                    "requer_auditoria_humana": False,
                    "justificativa_roteamento": "ok",
                    "regra_aplicada": "R-RECEITA",
                    "notificacao_gerada": None,
                },
            },
        ),
        "rejeitados/doc-oci-rej.json": (
            ONTEM,
            {
                "status": "rejeitado",
                "documento_id": "doc-oci-rej",
                "classificacao": {
                    "tipo_documento": LAUDO,
                    "especialidade": None,
                    "nivel_prioridade": "Rotina",
                    "score_confianca_classificacao": 0.2,
                },
                "problemas": ["ilegível"],
                "decisao_roteamento": {
                    "destino_principal": REVISAO,
                    "requer_auditoria_humana": True,
                    "justificativa_roteamento": "Motivo: ilegível",
                    "regra_aplicada": "R-REVISAO",
                    "notificacao_gerada": None,
                },
            },
        ),
    }

    class FakeOCI:
        def list_objects(self, ns, bucket, prefix="", fields=None, start=None):
            itens = [
                SimpleNamespace(name=nome, time_created=dt, time_modified=dt)
                for nome, (dt, _) in objetos.items()
                if nome.startswith(prefix)
            ]
            return SimpleNamespace(
                data=SimpleNamespace(objects=itens, next_start_with=None)
            )

        def get_object(self, ns, bucket, caminho):
            _, payload = objetos[caminho]
            bruto = json.dumps(payload).encode("utf-8")
            return SimpleNamespace(data=SimpleNamespace(content=bruto))

    monkeypatch.setenv("OCI_NAMESPACE", "ns-teste")
    monkeypatch.setattr(storage, "_cliente_oci", lambda: FakeOCI())

    r = client.get("/historico", params={"data_inicio": DIA_ANTERIOR, "data_fim": DIA})
    assert r.status_code == 200
    por_id = {item["documento_id"]: item for item in r.json()}
    assert set(por_id) == {"doc-oci-rot", "doc-oci-rej"}
    assert por_id["doc-oci-rot"]["chegada_em"] == HOJE.isoformat()
    assert por_id["doc-oci-rot"]["status"] == "processado"
    assert por_id["doc-oci-rej"]["chegada_em"] == ONTEM.isoformat()
    assert por_id["doc-oci-rej"]["status"] == "rejeitado"


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


# ---------- página 8_Historico.py (AppTest) ----------


def _pagina_historico() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parents[1] / "ui" / "pages" / "8_Historico.py")


class _RespHttp:
    def __init__(self, status: int = 200, corpo=None):
        self.status_code = status
        self._corpo = corpo

    def json(self):
        return self._corpo

    def raise_for_status(self) -> None:
        import requests

        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _preparar_ui_historico(monkeypatch, handler):
    import requests
    import streamlit as st

    st.cache_data.clear()
    monkeypatch.delenv("API_URL", raising=False)
    monkeypatch.setattr(requests, "get", handler)


def _item_historico(
    doc_id: str = "doc-ui-1",
    *,
    tipo: str | None = LAUDO,
    prioridade: str = "Urgente",
    destino: str = EMERGENCIA,
    status: str = "processado",
) -> dict:
    return {
        "documento_id": doc_id,
        "chegada_em": HOJE.isoformat(),
        "tipo": tipo,
        "prioridade": prioridade,
        "destino": destino,
        "status": status,
    }


def test_ui_historico_exibe_resultados_e_aplica_filtros(monkeypatch):
    from streamlit.testing.v1 import AppTest

    chamadas: list[list[tuple[str, str]]] = []

    def fake_get(url, params=None, **kw):
        assert url.endswith("/historico")
        chamadas.append(list(params or []))
        return _RespHttp(200, [_item_historico()])

    _preparar_ui_historico(monkeypatch, fake_get)

    at = AppTest.from_file(_pagina_historico(), default_timeout=30).run()
    assert not at.exception
    assert any("1 documento(s) encontrado(s)" in c.value for c in at.caption)

    df = at.dataframe[0].value
    assert df.iloc[0]["Documento"] == "doc-ui-1"
    assert df.iloc[0]["Chegada"] == "11/11/2026 12:00"
    assert df.iloc[0]["Destino"] == "Fila Emergencia Medica"
    assert df.iloc[0]["Status"] == "Processado"

    at.multiselect(key="hist_prioridades_0").select("Urgente")
    at.button[0].click().run()
    assert not at.exception
    assert ("prioridade", "Urgente") in chamadas[-1]


def test_ui_historico_estado_vazio_e_limpar_filtros(monkeypatch):
    from streamlit.testing.v1 import AppTest

    def fake_get(url, params=None, **kw):
        lista = list(params or [])
        tem_prioridade = any(chave == "prioridade" for chave, _ in lista)
        return _RespHttp(200, [] if tem_prioridade else [_item_historico()])

    _preparar_ui_historico(monkeypatch, fake_get)

    at = AppTest.from_file(_pagina_historico(), default_timeout=30).run()
    assert not at.exception

    at.multiselect(key="hist_prioridades_0").select("Urgente")
    at.button[0].click().run()
    assert not at.exception
    assert any("Nenhum documento encontrado." in i.value for i in at.info)

    btn_limpar = next(b for b in at.button if b.label == "Limpar filtros")
    btn_limpar.click().run()
    assert not at.exception
    assert at.session_state["filtro_versao"] == 1
    assert len(at.dataframe) == 1
    assert at.dataframe[0].value.iloc[0]["Documento"] == "doc-ui-1"


def test_ui_historico_exibe_motivo_de_rejeicao(monkeypatch):
    from streamlit.testing.v1 import AppTest

    itens = [
        _item_historico("doc-rej-1", status="rejeitado"),
        _item_historico("doc-rej-2", status="rejeitado"),
    ]

    def fake_get(url, **kw):
        if url.endswith("/historico"):
            return _RespHttp(200, itens)
        if url.endswith("/documentos/doc-rej-1"):
            return _RespHttp(200, {"motivo_rejeicao": "Documento ilegível"})
        if url.endswith("/documentos/doc-rej-2"):
            return _RespHttp(
                200,
                {
                    "decisao_roteamento": {
                        "justificativa_roteamento": "Rejeitado. Motivo: CRM inválido"
                    }
                },
            )
        raise AssertionError(f"URL inesperada: {url}")

    _preparar_ui_historico(monkeypatch, fake_get)

    at = AppTest.from_file(_pagina_historico(), default_timeout=30).run()
    assert not at.exception
    status_exibidos = list(at.dataframe[0].value["Status"])
    assert status_exibidos == [
        "Rejeitado — Documento ilegível",
        "Rejeitado — CRM inválido",
    ]


def test_ui_historico_exibe_aviso_em_422(monkeypatch):
    from streamlit.testing.v1 import AppTest

    detalhe = "A data de início deve ser anterior ou igual à de fim."
    _preparar_ui_historico(
        monkeypatch, lambda url, **kw: _RespHttp(422, {"detail": detalhe})
    )

    at = AppTest.from_file(_pagina_historico(), default_timeout=30).run()
    assert not at.exception
    assert any(detalhe in w.value for w in at.warning)


def test_ui_historico_exibe_erro_amigavel_em_falha_de_rede(monkeypatch):
    import requests
    from streamlit.testing.v1 import AppTest

    def erro_rede(url, **kw):
        raise requests.ConnectionError("API indisponível")

    _preparar_ui_historico(monkeypatch, erro_rede)

    at = AppTest.from_file(_pagina_historico(), default_timeout=30).run()
    assert not at.exception
    assert any("Não foi possível carregar o histórico." in e.value for e in at.error)
