"""T7: POST /triagem com o grafo e o armazenamento isolados (nada vai à nuvem)."""
import logging

import pytest

from app import storage
from testes.conftest import cliente_com, extracao

CORPO = {"documento_id": "DOC-CLIN-2026-8942", "tipo_arquivo": "PDF",
         "documento_texto": "LAUDO sintetico. Paciente: Fulano Sintetico de Souza, 52 anos.",
         "canal_origem": "Pronto_Socorro"}
CAMINHO = "recebidos/DOC-CLIN-2026-8942.txt"


class Espiao:
    """Extrator falso que anota o que recebeu: prova se o grafo rodou ou não."""
    def __init__(self):
        self.textos = []

    def __call__(self, texto):
        self.textos.append(texto)
        return extracao()


@pytest.fixture
def espiao():
    return Espiao()


@pytest.fixture
def client(espiao):
    return cliente_com(espiao)


# ---- cenário 1: envio válido ----
def test_envio_valido_retorna_202_com_id_e_recebido(client, espiao):
    r = client.post("/triagem", json=CORPO)
    assert r.status_code == 202
    assert r.json() == {"documento_id": CORPO["documento_id"], "status": "recebido"}
    assert storage.ler(CAMINHO).decode("utf-8") == CORPO["documento_texto"]
    assert espiao.textos == [CORPO["documento_texto"]]          # o grafo foi disparado


# ---- cenário 2: texto vazio ----
@pytest.mark.parametrize("texto", ["", "   ", "\n\t "])
def test_texto_vazio_retorna_422_e_nada_e_gravado_nem_processado(client, espiao, texto):
    r = client.post("/triagem", json={**CORPO, "documento_texto": texto})
    assert r.status_code == 422
    assert r.json() == {"detail": "documento vazio"}
    assert storage.listar("recebidos/") == []
    assert espiao.textos == []


# ---- segurança da entrada ----
@pytest.mark.parametrize("campo,valor", [
    ("documento_id", "../../fora"),
    ("documento_id", "a/b"),
    ("documento_id", "x" * 65),
    ("canal_origem", "<script>"),
    ("canal_origem", ""),
    pytest.param("documento_texto", "x" * 200_001, id="texto-acima-do-limite"),
])
def test_entrada_insegura_retorna_422_e_nada_e_gravado(client, espiao, campo, valor):
    r = client.post("/triagem", json={**CORPO, campo: valor})
    assert r.status_code == 422
    assert storage.listar("recebidos/") == []
    assert espiao.textos == []


def test_campo_ausente_retorna_422_em_portugues(client):
    corpo = {k: v for k, v in CORPO.items() if k != "canal_origem"}
    r = client.post("/triagem", json=corpo)
    assert r.status_code == 422
    assert r.json() == {"detail": "campo obrigatório ausente: canal_origem"}


def test_texto_no_limite_e_aceito(client):
    r = client.post("/triagem", json={**CORPO, "documento_texto": "x" * 200_000})
    assert r.status_code == 202


def test_id_repetido_retorna_409_sem_sobrescrever_e_sem_reprocessar(client, espiao):
    client.post("/triagem", json=CORPO)
    r = client.post("/triagem", json={**CORPO, "documento_texto": "outro texto"})
    assert r.status_code == 409
    assert storage.ler(CAMINHO).decode("utf-8") == CORPO["documento_texto"]
    assert len(espiao.textos) == 1


# ---- LGPD: o conteúdo clínico não pode ir para os logs ----
def test_conteudo_do_documento_nao_aparece_nos_logs(client, caplog):
    caplog.set_level(logging.DEBUG)
    client.post("/triagem", json=CORPO)
    client.post("/triagem", json={**CORPO, "documento_texto": "   "})          # 422
    assert caplog.records, "esperava ao menos o log de requisição"
    for trecho in ("Fulano", "Sintetico de Souza", "LAUDO sintetico", CORPO["documento_texto"]):
        assert trecho not in caplog.text
