"""H5.1.2 T4 — o resultado é gravado conforme a prioridade e a resposta só traz o caminho depois."""
import time

import pytest

from app import resposta, storage
from app.grafo import triar
from app.schemas import ResultadoTriagem
from testes.conftest import LAUDO_TEP, cliente_com, extracao, extrator_fixo


def _corpo(doc_id):
    return {"documento_id": doc_id, "tipo_arquivo": "TEXTO",
            "documento_texto": LAUDO_TEP, "canal_origem": "Pronto_Socorro"}


def test_urgente_grava_em_processados_urgentes(cliente):
    j = cliente.post("/triagem?aguardar=true", json=_corpo("DOC-RES-001")).json()
    arm = j["armazenamento_oci"]
    assert arm["caminho_objeto"] == "processados/urgentes/DOC-RES-001.json"
    assert arm["status_backup"] == "sucesso"
    assert arm["urgente"] is True                       # booleano no JSON, não texto
    assert storage.existe(arm["caminho_objeto"])


def test_rotina_grava_em_processados_rotina():
    c = cliente_com(extrator_fixo(extracao(nivel_prioridade="Rotina")))
    arm = c.post("/triagem?aguardar=true", json=_corpo("DOC-RES-002")).json()["armazenamento_oci"]
    assert arm["caminho_objeto"] == "processados/rotina/DOC-RES-002.json"
    assert arm["status_backup"] == "sucesso"
    assert arm["urgente"] is False
    assert storage.existe(arm["caminho_objeto"])


def test_o_que_foi_gravado_e_o_resultado_completo(cliente):
    cliente.post("/triagem?aguardar=true", json=_corpo("DOC-RES-003"))
    salvo = ResultadoTriagem.model_validate_json(storage.ler("processados/urgentes/DOC-RES-003.json"))
    assert salvo.documento_id == "DOC-RES-003"
    assert salvo.classificacao is not None and salvo.dados_extraidos is not None
    assert salvo.decisao_roteamento.destino_principal == "Fila_Emergencia_Medica"


@pytest.mark.parametrize("rota", ["/triagem/{}", "/documentos/{}"])
def test_consulta_devolve_o_armazenamento(cliente, rota):
    cliente.post("/triagem?aguardar=true", json=_corpo("DOC-RES-004"))
    arm = cliente.get(rota.format("DOC-RES-004")).json()["armazenamento_oci"]
    assert arm["caminho_objeto"] == "processados/urgentes/DOC-RES-004.json"
    assert arm["status_backup"] == "sucesso" and arm["urgente"] is True


def test_gravacao_em_menos_de_2_segundos_apos_a_decisao():
    estado = triar(LAUDO_TEP, extrator_fixo(extracao()), documento_id="DOC-RES-005")
    inicio = time.perf_counter()
    resposta.arquivar("DOC-RES-005", estado)
    assert time.perf_counter() - inicio < 2


def test_se_a_gravacao_falha_nao_ha_resposta_com_caminho(monkeypatch):
    estado = triar(LAUDO_TEP, extrator_fixo(extracao()), documento_id="DOC-RES-006")

    def gravar_quebrado(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(storage, "salvar", gravar_quebrado)
    with pytest.raises(OSError):
        resposta.arquivar("DOC-RES-006", estado)       # nada de caminho_objeto/status_backup inventado
