import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import storage
from app.api.rotas_original import router_original


@pytest.fixture
def cliente(monkeypatch):
    arquivos = {
        "recebidos/TXT-1.txt": "Receita fictícia\ncom acentuação".encode(),
        "recebidos/PDF-1.pdf": b"%PDF-1.4 conteudo binario \x00\xff",
        "recebidos/IMG-1.png": b"\x89PNG\r\n\x1a\n\x00\xff",
    }
    monkeypatch.setattr(storage, "ler", lambda caminho: arquivos.get(caminho))
    app = FastAPI()
    app.include_router(router_original)
    return TestClient(app), arquivos


def test_devolve_o_original_sem_alterar(cliente):
    c, arquivos = cliente
    for doc_id, caminho, tipo in [
        ("TXT-1", "recebidos/TXT-1.txt", "text/plain"),
        ("PDF-1", "recebidos/PDF-1.pdf", "application/pdf"),
        ("IMG-1", "recebidos/IMG-1.png", "image/png"),
    ]:
        resp = c.get(f"/documentos/{doc_id}/original")
        assert resp.status_code == 200
        assert resp.content == arquivos[caminho]  # byte a byte
        assert resp.headers["content-type"].startswith(tipo)
        assert resp.headers["x-content-type-options"] == "nosniff"


def test_inexistente_da_404_e_id_sujo_da_400(cliente):
    c, _ = cliente
    assert c.get("/documentos/NAO-EXISTE/original").status_code == 404
    assert c.get("/documentos/a.b/original").status_code == 400
