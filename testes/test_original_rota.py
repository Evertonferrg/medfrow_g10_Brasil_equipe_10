"""H3.4.1 T5 — bytes da rota idênticos ao objeto do bucket (dublê de storage)."""
import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.original import criar_router_original

PDF_BYTES = b"%PDF-1.4 conteudo binario \x00\xff\x10 qualquer"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00binario"

BUCKET = {"recebidos/doc-1.pdf": PDF_BYTES, "recebidos/doc-2.png": PNG_BYTES}
DOCS = {
    "doc-1": {"chave": "recebidos/doc-1.pdf", "content_type": "application/pdf", "nome_arquivo": "guia.pdf"},
    "doc-2": {"chave": "recebidos/doc-2.png", "nome_arquivo": "exame.png"},  # sem content_type
    "doc-3": {"chave": "recebidos/sumiu.pdf", "nome_arquivo": "sumiu.pdf"},
}


def _ler(chave: str) -> bytes:
    if chave not in BUCKET:
        raise FileNotFoundError(chave)
    return BUCKET[chave]


@pytest.fixture
def cliente():
    app = FastAPI()
    app.include_router(criar_router_original(DOCS.get, _ler))
    return TestClient(app)


def test_bytes_devolvidos_sao_identicos_ao_objeto(cliente):
    r = cliente.get("/documentos/doc-1/original")
    assert r.status_code == 200
    assert r.content == PDF_BYTES
    assert r.headers["content-type"] == "application/pdf"


def test_content_type_deduzido_do_nome_quando_ausente(cliente):
    r = cliente.get("/documentos/doc-2/original")
    assert r.content == PNG_BYTES
    assert r.headers["content-type"] == "image/png"


def test_documento_inexistente_devolve_404(cliente):
    assert cliente.get("/documentos/nao-existe/original").status_code == 404


def test_objeto_ausente_no_bucket_devolve_404(cliente):
    assert cliente.get("/documentos/doc-3/original").status_code == 404


def test_url_nao_permite_escolher_chave_arbitraria(cliente):
    assert cliente.get("/documentos/recebidos%2Fdoc-1.pdf/original").status_code == 404