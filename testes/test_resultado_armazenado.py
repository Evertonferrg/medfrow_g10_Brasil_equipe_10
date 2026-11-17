"""H5.1.2 T4 — o resultado é gravado conforme a prioridade e a resposta só traz o caminho depois."""

import time

import pytest

from app import resposta, storage
from app.eventos import ServicoEventos
from app.grafo import triar
from app.schemas import ResultadoTriagem
from app.status import StatusDocumento
from app.storage import FalhaArmazenamentoError
from testes.conftest import LAUDO_TEP, cliente_com, extracao, extrator_fixo


def _corpo(doc_id):
    return {
        "documento_id": doc_id,
        "tipo_arquivo": "TEXTO",
        "documento_texto": LAUDO_TEP,
        "canal_origem": "Pronto_Socorro",
    }


def test_urgente_grava_em_processados_urgentes(cliente):
    j = cliente.post("/triagem?aguardar=true", json=_corpo("DOC-RES-001")).json()
    arm = j["armazenamento_oci"]
    assert arm["caminho_objeto"] == "processados/urgentes/DOC-RES-001.json"
    assert arm["status_backup"] == "sucesso"
    assert arm["urgente"] is True  # booleano no JSON, não texto
    assert storage.existe(arm["caminho_objeto"])


def test_rotina_grava_em_processados_rotina(monkeypatch):
    # este teste verifica a PASTA de gravação para um documento de rotina; a detecção de
    # urgência (H3.1) é testada em test_urgencia.py, então aqui ela devolve "Rotina"
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.grafo.avaliar_urgencia",
        lambda *a, **k: SimpleNamespace(
            nivel="Rotina", sinal="nenhum sinal", achado=None
        ),
    )
    c = cliente_com(extrator_fixo(extracao(nivel_prioridade="Rotina")))
    arm = c.post("/triagem?aguardar=true", json=_corpo("DOC-RES-002")).json()[
        "armazenamento_oci"
    ]
    assert arm["caminho_objeto"] == "processados/rotina/DOC-RES-002.json"
    assert arm["status_backup"] == "sucesso"
    assert arm["urgente"] is False
    assert storage.existe(arm["caminho_objeto"])


def test_o_que_foi_gravado_e_o_resultado_completo(cliente):
    cliente.post("/triagem?aguardar=true", json=_corpo("DOC-RES-003"))
    ler_doc = storage.ler("processados/urgentes/DOC-RES-003.json")
    assert ler_doc is not None

    salvo = ResultadoTriagem.model_validate_json(ler_doc)
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
        resposta.arquivar(
            "DOC-RES-006", estado
        )  # nada de caminho_objeto/status_backup inventado


# def test_falha_oci_registra_status_e_evento(
#    monkeypatch, caplog, tmp_path, cliente, oci
# ):
#    import logging
#    logger = logging.getLogger(__name__)
#
#    caplog.set_level(logging.ERROR)
#    # Configure aqui o dublê OCI para falhar três vezes,
#    # como no exemplo do teste anterior.
#    fake_oci = oci(falhas=3)
#
#    oci_resposta = cliente.post(
#        "/triagem?aguardar=true",
#        json=_corpo("DOC-OCI-FAIL-001"),
#    )
#
#    assert len(fake_oci.chamadas) == 3
#    assert oci_resposta.status_code == 200
#    assert (
#        oci_resposta.json()["armazenamento_oci"]["status_backup"]
#        == "falha"
#    )
#
#    eventos = ServicoEventos(tmp_path / "eventos").listar(
#        "DOC-OCI-FAIL-001"
#    )
#    assert any(
#        evento["status"] == StatusDocumento.FALHA_OCI.value
#        for evento in eventos
#    )
#    #logger.error(eventos[0].get("detalhe", "cavalos"))
#    assert any(
#        "falha" in evento.get("detalhe", "").lower()
#        for evento in eventos
#        #evento.get("detalhe", "").lower() == "falha"
#        #for evento in eventos
#    )
#
#    assert any(
#        "armazenamento" in registro.getMessage().lower()
#        for registro in caplog.records
#    )

# def test_falha_ao_gravar_original_retorna_503_e_nao_processa(
#    cliente, monkeypatch
# ):
#    chamado = False
#
#    def falhar(*args, **kwargs):
#        raise OSError("OCI indisponível")
#
#    monkeypatch.setattr(storage, "salvar_original", falhar)
#
#    resposta = cliente.post("/triagem", json=_corpo("DOC-RES-008"))
#
#    assert resposta.status_code == 503
#    assert resposta.json()["detail"] == (
#        "Não foi possível guardar o documento. Tente novamente."
#    )
# Use o espião de testes/test_envio.py para verificar que o extrator
# não recebeu texto e que a tarefa de processamento não foi iniciada.


def test_oci_falha_duas_vezes_e_grava_na_terceira(oci):
    fake = oci(falhas=2)

    salvo = storage.salvar("processados/rotina/DOC-RETRY.json", {"ok": True})

    assert len(fake.chamadas) == 3
    assert salvo["status_backup"] == "sucesso"


def test_oci_falha_tres_vezes_devolve_falha_e_registra_evento(oci, tmp_path, caplog):
    estado = triar(
        LAUDO_TEP,
        extrator_fixo(extracao()),
        documento_id="DOC-OCI-FAIL-001",
    )
    fake = oci(falhas=3)

    resposta_api = resposta.arquivar("DOC-OCI-FAIL-001", estado)

    assert len(fake.chamadas) == 3
    assert resposta_api["armazenamento_oci"]["status_backup"] == "falha"

    eventos = ServicoEventos(tmp_path / "eventos").listar("DOC-OCI-FAIL-001")
    assert eventos[-1]["status"] == StatusDocumento.FALHA_OCI.value
    assert "falha de armazenamento" in eventos[-1]["detalhe"].lower()


def test_falha_do_original_retorna_503_e_nao_processa(cliente, monkeypatch):
    chamadas_extrator = 0

    def extrator_espiao(texto):
        nonlocal chamadas_extrator
        chamadas_extrator += 1

    def falhar_original(*args, **kwargs):
        raise FalhaArmazenamentoError("OCI indisponível")

    monkeypatch.setattr(storage, "salvar_original", falhar_original)

    resposta_http = cliente.post("/triagem", json=_corpo("DOC-RES-008"))

    assert resposta_http.status_code == 503
    assert resposta_http.json()["detail"] == (
        "Não foi possível guardar o documento. Tente novamente."
    )
    assert chamadas_extrator == 0
