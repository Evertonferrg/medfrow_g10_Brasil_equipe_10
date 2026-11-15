"""H5.1.1 T6 — o original é guardado antes de processar e nunca é sobrescrito."""

import pytest

from app import storage
from app.storage import ObjetoJaExisteError
from testes.conftest import (
    LAUDO_TEP,
    Erro412,
    cliente_com,
    extracao,
    extrator_que_quebra,
    pdf_com_texto,
)


def _corpo(doc_id):
    return {
        "documento_id": doc_id,
        "tipo_arquivo": "TEXTO",
        "documento_texto": LAUDO_TEP,
        "canal_origem": "Pronto_Socorro",
    }


# ---- critérios de aceite ----
def test_apos_o_envio_o_original_existe_em_recebidos(cliente):
    assert cliente.post("/triagem", json=_corpo("DOC-ORI-001")).status_code == 202
    ler_doc = storage.ler("recebidos/DOC-ORI-001.txt")
    assert ler_doc is not None and ler_doc.decode() == LAUDO_TEP


def test_se_a_triagem_falha_o_original_continua_la():
    c = cliente_com(extrator_que_quebra)
    assert (
        c.post("/triagem?aguardar=true", json=_corpo("DOC-ORI-002")).status_code == 200
    )
    assert storage.existe("recebidos/DOC-ORI-002.txt")


def test_original_de_pdf_fica_com_a_extensao_certa():
    c = cliente_com(extrator_que_quebra)
    pdf = pdf_com_texto(["Carlos Eduardo Mendes"])
    c.post(
        "/triagem/pdf",
        data={"documento_id": "DOC-ORI-003", "canal_origem": "X"},
        files={"arquivo": ("a.pdf", pdf, "application/pdf")},
    )
    assert storage.ler("recebidos/DOC-ORI-003.pdf") == pdf


# ---- T3: ordem gravação -> LLM ----
def test_o_llm_so_e_chamado_depois_da_gravacao():
    existia_na_chamada = []

    def extrator_espiao(texto):
        existia_na_chamada.append(storage.existe("recebidos/DOC-ORI-004.txt"))
        return extracao()

    cliente_com(extrator_espiao).post("/triagem", json=_corpo("DOC-ORI-004"))
    assert existia_na_chamada and all(
        existia_na_chamada
    )  # nunca chamou antes de gravar


def test_o_grafo_recebe_o_caminho_do_objeto_e_nao_o_arquivo(monkeypatch):
    chamadas = []

    def processar_falso(
        documento_id, texto, pdf_bytes, extrator, caminho_original=None
    ):
        chamadas.append((documento_id, texto, pdf_bytes, caminho_original))

    monkeypatch.setattr("app.api.main.processar", processar_falso)
    cliente_com(extrator_que_quebra).post("/triagem", json=_corpo("DOC-ORI-005"))
    assert chamadas == [("DOC-ORI-005", "", None, "recebidos/DOC-ORI-005.txt")]


# ---- T4: o original nunca é sobrescrito ----
def test_segunda_gravacao_do_mesmo_id_e_recusada():
    storage.salvar_original("DOC-ORI-006", b"%PDF-original", ".pdf")
    with pytest.raises(ObjetoJaExisteError):
        storage.salvar_original("DOC-ORI-006", b"%PDF-outro", ".pdf")
    assert (
        storage.ler("recebidos/DOC-ORI-006.pdf") == b"%PDF-original"
    )  # não foi trocado


def test_mesmo_id_em_outro_formato_tambem_e_recusado():
    storage.salvar_original("DOC-ORI-007", b"texto", ".txt")
    with pytest.raises(ObjetoJaExisteError):
        storage.salvar_original("DOC-ORI-007", b"%PDF-1.4", ".pdf")
    assert not storage.existe("recebidos/DOC-ORI-007.pdf")


def test_api_devolve_409_no_id_repetido(cliente):
    assert cliente.post("/triagem", json=_corpo("DOC-ORI-008")).status_code == 202
    r = cliente.post(
        "/triagem", json={**_corpo("DOC-ORI-008"), "documento_texto": "outro texto"}
    )
    assert r.status_code == 409
    ler_doc = storage.ler("recebidos/DOC-ORI-008.txt")
    assert ler_doc is not None and ler_doc.decode() == LAUDO_TEP


def test_extensao_desconhecida_e_recusada():
    with pytest.raises(ValueError):
        storage.salvar_original("DOC-ORI-009", b"x", ".exe")


@pytest.mark.parametrize(
    "extensao,conteudo,tipo",
    [
        (".pdf", b"%PDF-1.4", "application/pdf"),
        (".png", b"\x89PNG\r\n\x1a\n", "image/png"),
        (".jpg", b"\xff\xd8\xff\xe0", "image/jpeg"),
        (".txt", b"laudo", "text/plain; charset=utf-8"),
    ],
)
def test_oci_recebe_content_type_e_escrita_condicional(oci, extensao, conteudo, tipo):
    fake_oci = oci()
    r = storage.salvar_original("DOC-OCI-001", conteudo, extensao)
    assert (
        r["local"] == "oci"
        and r["caminho_objeto"] == f"recebidos/DOC-OCI-001{extensao}"
    )
    put = fake_oci.chamadas[0]
    assert put["content_type"] == tipo
    assert put["if_none_match"] == "*"


def test_oci_412_vira_objeto_ja_existe(oci):
    fake_oci = oci(erro=Erro412)
    with pytest.raises(ObjetoJaExisteError):
        storage.salvar_original("DOC-OCI-002", b"%PDF-1.4", ".pdf")
    assert len(fake_oci.chamadas) == 1
