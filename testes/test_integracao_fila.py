"""Rota registrada + índice real + eventos reais; só o carregamento do resultado é simulado."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ligacao_fila import ligar_fila_revisao
from app.eventos import ServicoEventos, registrar_desfecho
from app.indice_revisao import IndiceRevisao
from app.status import StatusDocumento as S


def resultado(
    doc_id, prioridade="Rotina", problemas=(), justificativa="Score baixo (0,40)"
):
    return {
        "status": "processado",
        "documento_id": doc_id,
        "classificacao": {
            "tipo_documento": "Receituário Médico",
            "nivel_prioridade": prioridade,
            "score_confianca_classificacao": 0.40,
        },
        "problemas": list(problemas),
        "decisao_roteamento": {
            "destino_principal": "Fila_Revisao_Humana",
            "requer_auditoria_humana": True,
            "justificativa_roteamento": justificativa,
        },
    }


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path / "eventos"))
    salvos = {}
    eventos = ServicoEventos(tmp_path / "eventos")
    app = FastAPI()
    ligar_fila_revisao(app, IndiceRevisao(eventos, carregar=salvos.get))
    return TestClient(app), eventos, salvos


def entra_em_revisao(eventos, salvos, doc_id, **kw):
    salvos[doc_id] = resultado(doc_id, **kw)
    eventos.registrar(doc_id, S.RECEBIDO)
    eventos.registrar(doc_id, S.EM_AUDITORIA_HUMANA)


def test_documento_com_score_baixo_aparece_na_fila_e_nao_da_404(ambiente):
    cliente, eventos, salvos = ambiente
    entra_em_revisao(eventos, salvos, "DOC-1")
    resp = cliente.get("/filas/revisao")
    assert resp.status_code == 200
    (caso,) = resp.json()
    assert caso["documento_id"] == "DOC-1"
    assert caso["motivos"] == [
        "Score baixo (0,40)"
    ]  # sem problemas: usa a justificativa
    assert caso["tipo"] == "Receituário Médico"
    assert caso["chegada_em"] == eventos.listar("DOC-1")[0]["em"]


def test_problemas_viram_motivos_e_todos_aparecem(ambiente):
    cliente, eventos, salvos = ambiente
    entra_em_revisao(
        eventos,
        salvos,
        "DOC-2",
        problemas=["CRM inválido", "Alto risco: morfina 500 mg."],
    )
    assert cliente.get("/filas/revisao").json()[0]["motivos"] == [
        "CRM inválido",
        "Alto risco: morfina 500 mg.",
    ]


def test_fila_ordena_urgente_antes_de_rotina(ambiente):
    cliente, eventos, salvos = ambiente
    entra_em_revisao(eventos, salvos, "ROT", prioridade="Rotina")
    entra_em_revisao(eventos, salvos, "URG", prioridade="Urgente")
    assert [c["documento_id"] for c in cliente.get("/filas/revisao").json()] == [
        "URG",
        "ROT",
    ]


def test_caso_decidido_sai_da_fila(ambiente):
    cliente, eventos, salvos = ambiente
    entra_em_revisao(eventos, salvos, "DOC-3")
    eventos.registrar("DOC-3", S.PROCESSADO)
    assert cliente.get("/filas/revisao").json() == []


def test_resultado_ilegivel_nao_derruba_a_fila(tmp_path):
    eventos = ServicoEventos(tmp_path)
    for doc in ("RUIM", "BOM"):
        eventos.registrar(doc, S.EM_AUDITORIA_HUMANA)

    def carregar(doc):
        if doc == "RUIM":
            raise ValueError("fora do formato")
        return resultado(doc)

    app = FastAPI()
    ligar_fila_revisao(app, IndiceRevisao(eventos, carregar=carregar))
    assert [
        c["documento_id"] for c in TestClient(app).get("/filas/revisao").json()
    ] == ["BOM"]


def test_fila_vazia_sem_eventos(ambiente):
    assert ambiente[0].get("/filas/revisao").json() == []


def test_registrar_desfecho_manda_revisao_para_a_fila_e_o_resto_para_processado(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path))
    revisao = SimpleNamespace(
        decisao_roteamento=SimpleNamespace(destino_principal="Fila_Revisao_Humana")
    )
    farmacia = SimpleNamespace(
        decisao_roteamento=SimpleNamespace(destino_principal="Farmacia_Hospitalar")
    )
    registrar_desfecho("R1", revisao)
    registrar_desfecho("F1", farmacia)
    ev = ServicoEventos(tmp_path)
    assert ev.status_atual("R1") == S.EM_AUDITORIA_HUMANA
    assert ev.status_atual("F1") == S.PROCESSADO
