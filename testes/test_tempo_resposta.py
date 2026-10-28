"""T8: o POST /triagem (sem aguardar=true) responde em até 2 s e cada requisição é logada."""
import logging
import time

from app.api import tempo
from testes.conftest import cliente_com, extracao, extrator_fixo

LIMITE_S = 2.0
LOG = "mediflow.requisicoes"
CORPO = {"documento_id": "TEMPO-001", "tipo_arquivo": "TEXTO",
         "documento_texto": "LAUDO sintetico de teste.", "canal_origem": "Ambulatorio"}


def _registros(caplog):
    return [r for r in caplog.records if r.name == LOG]


def test_post_sem_aguardar_responde_em_menos_de_2s():
    c = cliente_com(extrator_fixo(extracao()))
    inicio = time.perf_counter()
    r = c.post("/triagem", json=CORPO)
    assert r.status_code == 202
    assert time.perf_counter() - inicio < LIMITE_S


def test_resposta_nao_espera_o_llm(caplog):
    """Um LLM lento (1,5 s) não pode atrasar a resposta: o grafo roda depois."""
    caplog.set_level(logging.INFO, logger=LOG)

    def llm_lento(texto):
        time.sleep(1.5)
        return extracao()

    r = cliente_com(llm_lento).post("/triagem", json=CORPO)
    assert r.status_code == 202
    registro = _registros(caplog)[0]
    assert registro.duracao_ms < 1000          # respondeu antes de o LLM terminar
    assert registro.duracao_ms < LIMITE_S * 1000


def test_cada_requisicao_gera_um_log_com_a_duracao(caplog):
    caplog.set_level(logging.INFO, logger=LOG)
    c = cliente_com(extrator_fixo(extracao()))
    c.post("/triagem", json=CORPO)
    c.get("/triagem/TEMPO-001")
    registros = _registros(caplog)
    assert len(registros) == 2
    post = registros[0]
    assert (post.metodo, post.caminho, post.status_http) == ("POST", "/triagem", 202)
    assert post.duracao_ms >= 0
    assert "ms" in post.getMessage()


def test_requisicao_acima_do_limite_gera_warning(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=LOG)
    monkeypatch.setattr(tempo, "LIMITE_MS", -1)           # tudo passa a estar "acima do limite"
    cliente_com(extrator_fixo(extracao())).post("/triagem", json=CORPO)
    assert _registros(caplog)[0].levelno == logging.WARNING


def test_log_nao_registra_query_string_nem_corpo(caplog):
    caplog.set_level(logging.INFO, logger=LOG)
    c = cliente_com(extrator_fixo(extracao()))
    c.post("/triagem?token=segredo123", json=CORPO)
    assert "segredo123" not in caplog.text
    assert CORPO["documento_texto"] not in caplog.text


def test_log_nao_aceita_injecao_de_quebra_de_linha(caplog):
    caplog.set_level(logging.INFO, logger=LOG)
    cliente_com(extrator_fixo(extracao())).get("/triagem/abc%0AINJETADO")
    mensagem = _registros(caplog)[0].getMessage()
    assert "\n" not in mensagem


def test_limpar_troca_caracteres_estranhos():
    assert tempo.limpar("/a\nb\r\x00ç") == "/a?b???"
    assert len(tempo.limpar("/" + "x" * 500)) == 200
