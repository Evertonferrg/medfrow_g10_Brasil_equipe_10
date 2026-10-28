"""H1.3.5: exames e procedimentos solicitados."""
import pytest
from fastapi.testclient import TestClient

from app.api import criar_app
from app.llm import PROMPT
from app.schemas import Exame, Extracao, Medico, Paciente
from app.validacao import validar
from testes.fixtures import guias as G


def ext(exames) -> Extracao:
    return Extracao(
        tipo_documento="Guia de Solicitação de Procedimento", especialidade="Ortopedia",
        nivel_prioridade="Rotina", score_confianca_classificacao=0.95,
        paciente=Paciente(nome="Joao Pereira"),
        medico_solicitante=Medico(nome="Dra. Ana Torres", crm="CRM-RJ 100002"),
        exames=[Exame(**e) for e in exames])


JOELHO = "Ressonancia magnetica de joelho"
ABDOME = "Ultrassonografia de abdome total"


def pares(e):
    return [(x.nome, x.codigo_tuss) for x in e.exames]


# ---------------- critérios de aceite ----------------
def test_guia_com_dois_exames_mostra_cada_um_separado():
    e, problemas, score = validar(ext([{"nome": JOELHO}, {"nome": ABDOME}]), G.GUIA_2_EXAMES)
    assert pares(e) == [(JOELHO, None), (ABDOME, None)] and problemas == [] and score == 0.95


def test_codigo_tuss_escrito_aparece_junto_do_exame():
    e, problemas, _ = validar(ext([{"nome": JOELHO, "codigo_tuss": "40801020"},
                                   {"nome": ABDOME, "codigo_tuss": "40901017"}]), G.GUIA_COM_TUSS)
    assert pares(e) == [(JOELHO, "40801020"), (ABDOME, "40901017")] and problemas == []


# ---------------- TUSS: nunca inventado ----------------
def test_tuss_inventado_e_descartado():
    e, problemas, _ = validar(ext([{"nome": JOELHO, "codigo_tuss": "99999999"}]), G.GUIA_COM_TUSS)
    assert e.exames[0].codigo_tuss is None and any("não encontrado" in p for p in problemas)


def test_tuss_escrito_com_pontuacao_vira_so_digitos():
    e, problemas, _ = validar(ext([{"nome": JOELHO, "codigo_tuss": "4.08.01.02-0"}]), G.GUIA_COM_TUSS)
    assert e.exames[0].codigo_tuss == "40801020" and problemas == []


def test_tuss_nao_casa_com_pedaco_de_outro_numero():
    texto = G.CABECALHO + f"Procedimentos: {JOELHO}. Protocolo 140801020."
    e, problemas, _ = validar(ext([{"nome": JOELHO, "codigo_tuss": "40801020"}]), texto)
    assert e.exames[0].codigo_tuss is None and problemas


def test_tuss_trocado_entre_exames_e_descartado():
    e, problemas, _ = validar(ext([{"nome": JOELHO, "codigo_tuss": "40901017"},     # código do outro
                                   {"nome": ABDOME, "codigo_tuss": "40801020"}]), G.GUIA_COM_TUSS)
    assert pares(e) == [(JOELHO, None), (ABDOME, None)]
    assert sum("não está junto" in p for p in problemas) == 2


def test_guia_de_um_exame_aceita_o_codigo_em_qualquer_lugar_do_texto():
    texto = G.CABECALHO + f"Procedimento: {JOELHO}. Observacao longa " + "x " * 400 + "Codigo TUSS 40801020."
    e, problemas, _ = validar(ext([{"nome": JOELHO, "codigo_tuss": "40801020"}]), texto)
    assert e.exames[0].codigo_tuss == "40801020" and problemas == []


# ---------------- duplicatas, nome e inventados ----------------
def test_exame_repetido_vira_um_item_so():
    e, _, _ = validar(ext([{"nome": JOELHO}, {"nome": "ressonancia MAGNETICA de joelho"}]), G.GUIA_REPETIDA)
    assert len(e.exames) == 1


def test_duplicata_nao_faz_perder_o_codigo_tuss():
    e, _, _ = validar(ext([{"nome": JOELHO}, {"nome": JOELHO.upper(), "codigo_tuss": "40801020"}]),
                      G.GUIA_COM_TUSS)
    assert pares(e)[0] == (JOELHO, "40801020")


def test_exame_inventado_e_descartado_e_sinalizado():
    e, problemas, _ = validar(ext([{"nome": JOELHO}, {"nome": "Tomografia de cranio"}]), G.GUIA_2_EXAMES)
    assert [x.nome for x in e.exames] == [JOELHO]
    assert any("Tomografia de cranio" in p and "não encontrado" in p for p in problemas)


# ---------------- pela API e prompt ----------------
@pytest.fixture(autouse=True)
def _storage_local(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path / "storage"))
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)


def test_guia_de_rotina_vai_para_a_auditoria_com_exames_e_medico():
    extracao = ext([{"nome": JOELHO, "codigo_tuss": "40801020"}, {"nome": ABDOME, "codigo_tuss": "40901017"}])
    client = TestClient(criar_app(lambda t: extracao))
    r = client.post("/triagem?aguardar=true", json={
        "documento_id": "GUIA-0001", "tipo_arquivo": "TEXTO", "documento_texto": G.GUIA_COM_TUSS,
        "canal_origem": "Ambulatorio"})
    j = r.json()
    assert j["decisao_roteamento"]["destino_principal"] == "Auditoria_Autorizacoes"
    assert [(x["nome"], x["codigo_tuss"]) for x in j["dados_extraidos"]["exames"]] == [
        (JOELHO, "40801020"), (ABDOME, "40901017")]
    assert j["dados_extraidos"]["medico_solicitante"]["crm"] == "100002-RJ"


def test_prompt_traz_as_regras_dos_exames():
    p = PROMPT
    for trecho in ("CADA exame", "nunca agrupado", "nunca invente nem complete um código"):
        assert trecho in p
