import time
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ligacao_documentos import ligar_documentos
from app.indice_documentos import IndiceDocumentos, ResumoDocumento

BASE = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)


def _resumo(i, canal="Ambulatorio"):
    return ResumoDocumento(
        documento_id=f"DOC-{i:03d}",
        tipo_documento="Receituário Médico",
        nivel_prioridade="Rotina",
        destino="Fila_Farmacia",
        status="Processado",
        data=BASE + timedelta(minutes=i),
        canal_origem=canal,
    )


def _cliente(indice):
    app = FastAPI()
    ligar_documentos(app, indice)
    return TestClient(app)


def test_dez_documentos_em_ordem_decrescente_de_data():
    indice = IndiceDocumentos()
    indice.reconstruir(_resumo(i) for i in range(10))
    itens = _cliente(indice).get("/documentos").json()
    assert len(itens) == 10
    datas = [i["data"] for i in itens]
    assert datas == sorted(datas, reverse=True)
    assert itens[0]["documento_id"] == "DOC-009"


def test_filtro_por_canal_origem():
    indice = IndiceDocumentos()
    indice.reconstruir(
        [
            _resumo(1, "Laboratorio"),
            _resumo(2, "Ambulatorio"),
            _resumo(3, "Laboratorio"),
        ]
    )
    itens = (
        _cliente(indice)
        .get("/documentos", params={"canal_origem": "Laboratorio"})
        .json()
    )
    assert {i["documento_id"] for i in itens} == {"DOC-001", "DOC-003"}


def test_atualizar_muda_o_status_sem_duplicar():
    indice = IndiceDocumentos()
    indice.atualizar(_resumo(1))
    indice.atualizar(_resumo(1).model_copy(update={"status": "Em revisão"}))
    itens = indice.listar()
    assert len(itens) == 1 and itens[0].status == "Em revisão"


def test_listagem_de_100_documentos_responde_em_menos_de_3s():
    indice = IndiceDocumentos()
    indice.reconstruir(_resumo(i) for i in range(100))
    cliente = _cliente(indice)
    inicio = time.perf_counter()
    itens = cliente.get("/documentos").json()
    assert time.perf_counter() - inicio < 3
    assert len(itens) == 100
