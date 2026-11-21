"""H3.4.1 T3/T5 — componentes da página do caso e reset do Dashboard."""

from pathlib import Path

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from ui.componentes.caso import VAZIO, dados_do_caso
from ui.componentes.original import paginas_do_original

PAGINA_DASHBOARD = str(
    Path(__file__).resolve().parents[1] / "ui" / "pages" / "3_Dashboard.py"
)


def test_dados_do_caso_completo():
    d = dados_do_caso(
        {
            "paciente": {"nome": "Maria Souza", "idade": 54},
            "origem": "Hospital X",
            "achado_principal": "Nódulo pulmonar 2,3 cm",
            "cid": "R91",
            "medico_solicitante": "Dr. João",
        }
    )
    assert d == {
        "paciente": "Maria Souza",
        "origem": "Hospital X",
        "achado": "Nódulo pulmonar 2,3 cm",
        "cid": "R91",
        "medico": "Dr. João",
    }


def test_dados_ausentes_viram_traco():
    d = dados_do_caso({"paciente": "Ana"})
    assert d["paciente"] == "Ana"
    assert d["cid"] == d["medico"] == d["origem"] == d["achado"] == VAZIO


def test_formato_real_da_api_com_dados_extraidos():
    d = dados_do_caso(
        {
            "status": "ok",
            "canal_origem": "email",
            "dados_extraidos": {
                "paciente": "Maria Souza",
                "medico_solicitante": "Dr. João",
                "diagnostico_principal": "Nódulo pulmonar",
                "cid": "não encontrado",
                "cid_sugerido": "R91",
            },
        }
    )
    assert d == {
        "paciente": "Maria Souza",
        "origem": "email",
        "achado": "Nódulo pulmonar",
        "cid": "R91",
        "medico": "Dr. João",
    }


def test_imagem_e_devolvida_como_esta():
    assert paginas_do_original(b"\x89PNG...", "image/png") == [b"\x89PNG..."]


def test_content_type_com_parametros_e_aceito():
    assert paginas_do_original(b"jpg", "image/jpeg; charset=binary") == [b"jpg"]


def test_tipo_nao_suportado_levanta_valueerror():
    with pytest.raises(ValueError):
        paginas_do_original(b"x", "application/zip")


def test_pdf_vira_uma_png_por_pagina():
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page().insert_text((72, 72), "teste")
    paginas = paginas_do_original(doc.tobytes(), "application/pdf")
    assert len(paginas) == 3
    assert all(p.startswith(b"\x89PNG") for p in paginas)


def test_pdf_respeita_max_paginas():
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for _ in range(5):
        doc.new_page()
    assert (
        len(paginas_do_original(doc.tobytes(), "application/pdf", max_paginas=2)) == 2
    )


class _RespDashboard:
    """Resposta falsa das rotas GET da API usadas por 3_Dashboard.py."""

    def __init__(
        self,
        status: int,
        corpo=None,
        content: bytes = b"",
        headers: dict | None = None,
    ):
        self.status_code = status
        self._corpo = corpo
        self.text = ""
        self.content = content
        self.headers = headers or {}

    def json(self):
        if self._corpo is None:
            raise ValueError("sem json")
        return self._corpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _resultado_dashboard(
    doc_id: str = "DOC-1", *, requer_revisao: bool = False
) -> dict:
    return {
        "status": "processado",
        "documento_id": doc_id,
        "classificacao": {"tipo_documento": "Receituário Médico"},
        "decisao_roteamento": {
            "destino_principal": (
                "Fila_Revisao_Humana" if requer_revisao else "Farmacia_Hospitalar"
            ),
            "requer_auditoria_humana": requer_revisao,
        },
        "dados_extraidos": {},
    }


def _mock_api_dashboard(
    monkeypatch,
    *,
    doc_resp=None,
    lista_docs=None,
    original_resp=None,
):
    st.cache_data.clear()
    monkeypatch.delenv("API_URL", raising=False)

    def falso_get(url: str, **kw):
        if url.endswith("/original"):
            return original_resp if original_resp is not None else _RespDashboard(404)
        if url.rstrip("/").endswith("/documentos"):
            return _RespDashboard(200, lista_docs if lista_docs is not None else [])
        if isinstance(doc_resp, Exception):
            raise doc_resp
        return (
            doc_resp
            if doc_resp is not None
            else _RespDashboard(200, _resultado_dashboard())
        )

    monkeypatch.setattr(requests, "get", falso_get)


def test_dashboard_tela_vazia_mostra_busca_manual(monkeypatch):
    _mock_api_dashboard(monkeypatch)
    at = AppTest.from_file(PAGINA_DASHBOARD, default_timeout=30).run()
    assert not at.exception
    assert any("Digite o ID de um documento" in i.value for i in at.info)
    assert len(at.text_input) == 1
    assert any("Abrir Caso" in b.label for b in at.button)


def test_dashboard_estado_processando_202_exibe_aviso(monkeypatch):
    _mock_api_dashboard(monkeypatch, doc_resp=_RespDashboard(202))
    at = AppTest.from_file(PAGINA_DASHBOARD, default_timeout=30)
    at.session_state["caso_id"] = "DOC-PROC"
    at.run()
    assert not at.exception
    assert any("Analisando o documento **DOC-PROC**" in i.value for i in at.info)


@pytest.mark.parametrize(
    "resposta,canal_msg,trecho_esperado",
    [
        (_RespDashboard(404), "warning", "Documento não encontrado"),
        (_RespDashboard(400), "error", "ID de documento inválido"),
        (
            requests.ConnectionError("sem rede"),
            "error",
            "Não foi possível consultar a API",
        ),
    ],
)
def test_dashboard_trata_erros_da_api(
    monkeypatch, resposta, canal_msg, trecho_esperado
):
    _mock_api_dashboard(monkeypatch, doc_resp=resposta)
    at = AppTest.from_file(PAGINA_DASHBOARD, default_timeout=30)
    at.session_state["caso_id"] = "DOC-ERRO"
    at.run()
    assert not at.exception
    mensagens = [m.value for m in getattr(at, canal_msg)]
    assert any(trecho_esperado in m for m in mensagens)


def test_dashboard_exibe_original_texto_e_origem_do_caso(monkeypatch):
    _mock_api_dashboard(
        monkeypatch,
        doc_resp=_RespDashboard(200, _resultado_dashboard("DOC-ORIG")),
        lista_docs=[{"documento_id": "DOC-ORIG", "canal_origem": "Pronto_Socorro"}],
        original_resp=_RespDashboard(
            200,
            content=b"LAUDO ORIGINAL SINTETICO",
            headers={"content-type": "text/plain; charset=utf-8"},
        ),
    )
    at = AppTest.from_file(PAGINA_DASHBOARD, default_timeout=30)
    at.session_state["caso_id"] = "DOC-ORIG"
    at.run()
    assert not at.exception
    assert any(
        "Documento DOC-ORIG" in c.value and "Origem: Pronto_Socorro" in c.value
        for c in at.caption
    )
    assert any("LAUDO ORIGINAL SINTETICO" in t.value for t in at.text)


def test_dashboard_original_indisponivel_exibe_aviso(monkeypatch):
    _mock_api_dashboard(
        monkeypatch,
        doc_resp=_RespDashboard(200, _resultado_dashboard("DOC-SEM-ORIG")),
        original_resp=_RespDashboard(404),
    )
    at = AppTest.from_file(PAGINA_DASHBOARD, default_timeout=30)
    at.session_state["caso_id"] = "DOC-SEM-ORIG"
    at.run()
    assert not at.exception
    assert any("Documento original indisponível." in i.value for i in at.info)


def test_dashboard_banner_revisar_caso_chama_abrir_revisao(monkeypatch):
    _mock_api_dashboard(
        monkeypatch,
        doc_resp=_RespDashboard(
            200, _resultado_dashboard("DOC-REV", requer_revisao=True)
        ),
    )
    destinos_navegados: list[str] = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinos_navegados.append(page))

    at = AppTest.from_file(PAGINA_DASHBOARD, default_timeout=30)
    at.session_state["caso_id"] = "DOC-REV"
    at.run()
    assert not at.exception
    assert any(
        "Este caso precisa de revisão humana." in m.value for m in at.markdown
    )

    at.button(key="btn_revisar").click().run()
    assert not at.exception
    assert destinos_navegados == ["pages/13_UI_Revisao_de_Caso.py"]
    assert at.session_state["caso_id"] == "DOC-REV"
    assert at.session_state["_id_para_url"] == "DOC-REV"


def test_dashboard_botao_consultar_outro_documento_volta_a_busca_manual(monkeypatch):
    _mock_api_dashboard(
        monkeypatch,
        doc_resp=_RespDashboard(200, _resultado_dashboard("DOC-1")),
    )

    at = AppTest.from_file(PAGINA_DASHBOARD, default_timeout=30)
    at.session_state["caso_id"] = "DOC-1"
    at.session_state["ultimo_documento_id"] = "DOC-1"
    at.run()
    assert not at.exception

    at.button(key="btn_novo_caso").click().run()
    assert not at.exception
    assert "caso_id" not in at.session_state
    assert "ultimo_documento_id" not in at.session_state
    assert "id" not in at.query_params
    assert len(at.text_input) == 1
    assert any("Abrir Caso" in b.label for b in at.button)
