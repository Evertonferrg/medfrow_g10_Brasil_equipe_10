"""Testes da fila de revisão (H4.2.1 e H4.2.2). Prioridade como texto, sem depender de H3.1.3."""

import time
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import rotas_status_fila as r
from app.fila import CasoRevisao, ordenar_fila


class N:
    PRIORITARIO = "Prioritário"
    ROTINA = "Rotina"


T0 = datetime(2026, 11, 6, 8, 0, tzinfo=UTC)


def caso(i, prio, minutos, motivos=("dúvida",)):
    return CasoRevisao(
        f"d{i}", "receita", list(motivos), T0 + timedelta(minutes=minutos), prio
    )


class IndiceDuble:
    def __init__(self, casos):
        self.casos = casos

    def listar_casos_revisao(self):
        return self.casos


def _cliente(casos):
    app = FastAPI()
    app.include_router(r.router)
    app.dependency_overrides[r.get_indice_revisao] = lambda: IndiceDuble(casos)
    return TestClient(app)


def test_prioritario_vem_primeiro():
    fila = ordenar_fila(
        [caso(1, N.ROTINA, 0), caso(2, N.ROTINA, 1), caso(3, N.PRIORITARIO, 5)]
    )
    assert fila[0].documento_id == "d3"


def test_mesma_prioridade_mais_antigo_primeiro():
    fila = ordenar_fila(
        [caso(1, N.ROTINA, 30), caso(2, N.ROTINA, 10), caso(3, N.ROTINA, 20)]
    )
    assert [c.documento_id for c in fila] == ["d2", "d3", "d1"]


def test_cinco_casos_aparecem_os_cinco_com_campos():
    resp = _cliente([caso(i, N.ROTINA, i) for i in range(5)]).get("/filas/revisao")
    dados = resp.json()
    assert len(dados) == 5 and {"tipo", "motivos", "chegada_em"} <= set(dados[0])


def test_caso_com_dois_motivos_mostra_os_dois():
    dados = (
        _cliente([caso(1, N.ROTINA, 0, ("CRM inválido", "alto risco"))])
        .get("/filas/revisao")
        .json()
    )
    assert dados[0]["motivos"] == ["CRM inválido", "alto risco"]


def test_listagem_de_50_casos_abaixo_de_3s():
    c = _cliente([caso(i, N.ROTINA, i) for i in range(50)])
    t = time.perf_counter()
    assert len(c.get("/filas/revisao").json()) == 50
    assert time.perf_counter() - t < 3
