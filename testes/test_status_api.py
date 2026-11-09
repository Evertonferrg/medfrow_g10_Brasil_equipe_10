import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import rotas_status_fila as r
from app.eventos import ServicoEventos
from app.status import StatusDocumento as S


class ResultadosDuble:
    def obter(self, documento_id):
        return {"tipo": "receita"}


def _cliente(tmp_path):
    app = FastAPI()
    app.include_router(r.router)
    ev = ServicoEventos(tmp_path)
    app.dependency_overrides[r.get_eventos] = lambda: ev
    app.dependency_overrides[r.get_resultados] = lambda: ResultadosDuble()
    return TestClient(app), ev


def test_id_existente_devolve_status(tmp_path):
    c, ev = _cliente(tmp_path)
    ev.registrar("abc", S.PROCESSADO)
    resp = c.get("/documentos/abc")
    assert resp.status_code == 200 and resp.json()["status"] == "processado"


def test_id_inexistente_devolve_404(tmp_path):
    c, _ = _cliente(tmp_path)
    resp = c.get("/documentos/nao-existe")
    assert (
        resp.status_code == 404 and resp.json()["detail"] == "documento não encontrado"
    )


def test_consulta_abaixo_de_2s(tmp_path):
    c, ev = _cliente(tmp_path)
    ev.registrar("abc", S.RECEBIDO)
    t = time.perf_counter()
    c.get("/documentos/abc")
    assert time.perf_counter() - t < 2


def test_nenhuma_rota_publica_altera_status():  # T3
    for rota in r.router.routes:
        if "status" in rota.path or rota.path.startswith("/documentos"):
            assert rota.methods <= {"GET", "HEAD"}
