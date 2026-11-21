import pytest

from ui.componentes.revisao import (
    campos_inconsistentes,
    evidencia_do_campo,
    motivo_destaque,
    precisa_destaque,
)


@pytest.mark.parametrize(
    ("score", "inconsistente", "esperado"),
    [
        (0.79, False, True),  # abaixo do limite
        (0.8, False, False),  # igual ao limite: não destaca
        (0.95, False, False),  # acima
        (0.95, True, True),  # inconsistente, mesmo com score alto
        (None, False, False),  # sem score
    ],
)
def test_precisa_destaque(score, inconsistente, esperado):
    assert precisa_destaque(score, inconsistente, 0.8) is esperado


def test_motivo_em_texto():
    assert motivo_destaque(0.3, False, 0.8) == "abaixo do limite (0.30)"
    assert motivo_destaque(0.3, True, 0.8) == "inconsistente"
    assert motivo_destaque(0.9, False, 0.8) is None


def test_campos_inconsistentes_pelos_problemas():
    problemas = [
        "CRM em formato inválido: '12345-XX'",
        "Inconsistência: A idade informada (30 anos) diverge da data de nascimento (12/03/1950).",
        "Inconsistência: O CID-10 informado é inconsistente com o diagnóstico principal.",
        "Receita emitida na unidade central",  # sem sinal de alerta: ignora
    ]
    assert campos_inconsistentes(problemas) == {
        "crm",
        "idade",
        "data_nascimento",
        "cid",
        "diagnostico",
    }
    assert campos_inconsistentes(None) == set()


def test_evidencia_do_campo():
    dados = {
        "evidencias": [
            {"campo": "crm", "trecho": "CRM 12345-XX"},
            {"campo": "x", "trecho": ""},
        ]
    }
    assert evidencia_do_campo(dados, "crm", "medico_solicitante.crm") == "CRM 12345-XX"
    assert evidencia_do_campo(dados, "idade") is None


# ---------- página 13_UI_Revisao_de_Caso.py (AppTest) ----------


def _pagina_revisao() -> str:
    from pathlib import Path

    return str(
        Path(__file__).resolve().parents[1]
        / "ui"
        / "pages"
        / "13_UI_Revisao_de_Caso.py"
    )


class _RespHttp:
    def __init__(
        self,
        status: int = 200,
        corpo=None,
        *,
        content: bytes = b"",
        headers: dict | None = None,
    ):
        self.status_code = status
        self._corpo = corpo
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._corpo


def _caso_revisao(doc_id: str = "DOC-REV-1") -> dict:
    return {
        "documento_id": doc_id,
        "status_documento": "em_auditoria_humana",
        "classificacao": {
            "tipo_documento": "Receituário Médico",
            "score_confianca_classificacao": 0.65,
        },
        "decisao_roteamento": {
            "destino_principal": "Fila_Revisao_Humana",
            "justificativa_roteamento": "Confiança abaixo do limite.",
        },
        "problemas": [
            "CRM em formato inválido: '12345-XX'",
            "Inconsistência: A idade informada diverge da data de nascimento.",
        ],
        "dados_extraidos": {
            "paciente": {
                "nome": "João da Silva",
                "idade": 30,
                "data_nascimento": "12/03/1950",
            },
            "medico_solicitante": {"nome": "Dra. Ana", "crm": "12345-XX"},
            "diagnostico_principal": "Hipertensão",
            "cid_sugerido": "I10",
            "medicamentos": [{"nome": "Losartana", "dose": None, "via": "Oral"}],
            "evidencias": [{"campo": "crm", "trecho": "CRM 12345-XX"}],
        },
    }


def _trilha_exemplo() -> dict:
    return {
        "cadeia_integra": True,
        "eventos": [
            {
                "autor_tipo": "agente",
                "status": "em_auditoria_humana",
                "em": "2026-11-11T15:00:00+00:00",
                "regra_aplicada": "R-REVISAO",
                "detalhe": "Enviado para auditoria humana.",
            },
            {
                "autor_tipo": "auditora",
                "autor_nome": "Dra. Renata Silveira",
                "status": "em_revisao",
                "em": "2026-11-11T15:05:00+00:00",
                "campo": "destino",
                "valor_anterior": "Fila_Revisao_Humana",
                "valor_novo": "Farmacia_Hospitalar",
            },
        ],
    }


def _mock_get_completo(doc_id: str = "DOC-REV-1"):
    def fake_get(url, **kw):
        if url.endswith(f"/documentos/{doc_id}"):
            return _RespHttp(200, _caso_revisao(doc_id))
        if url.endswith(f"/documentos/{doc_id}/original"):
            return _RespHttp(
                200,
                content=b"Receita medica: Losartana 50mg",
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        if url.endswith(f"/documentos/{doc_id}/trilha"):
            return _RespHttp(200, _trilha_exemplo())
        if url.endswith("/regras/destinos"):
            return _RespHttp(
                200,
                {
                    "destinos": [
                        "Fila_Revisao_Humana",
                        "Farmacia_Hospitalar",
                        "Fila_Emergencia_Medica",
                    ]
                },
            )
        raise AssertionError(f"URL inesperada: {url}")

    return fake_get


def _abrir_revisao(monkeypatch, doc_id: str | None = "DOC-REV-1", get_fn=None):
    import requests
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("API_URL", raising=False)
    monkeypatch.setattr(
        requests, "get", get_fn or _mock_get_completo(doc_id or "DOC-REV-1")
    )
    at = AppTest.from_file(_pagina_revisao(), default_timeout=30)
    if doc_id is not None:
        at.query_params["id"] = doc_id
    return at.run()


def test_ui_revisao_sem_documento_exibe_orientacao(monkeypatch):
    at = _abrir_revisao(monkeypatch, doc_id=None)
    assert not at.exception
    assert any("Abra um caso pela fila de revisão." in i.value for i in at.info)


def test_ui_revisao_carrega_caso_original_destaques_e_trilha(monkeypatch):
    at = _abrir_revisao(monkeypatch)
    assert not at.exception

    assert any("Receita medica: Losartana 50mg" in t.value for t in at.text)
    markdowns = [m.value for m in at.markdown]
    assert any("Confiança 0.65" in m for m in markdowns)
    assert any("CRM em formato inválido" in m for m in markdowns)
    assert any(
        "rv-alerta" in m and "inconsistente" in m and "Evidência: CRM 12345-XX" in m
        for m in markdowns
    )
    assert any("Losartana" in m and "sem dose" in m for m in markdowns)
    assert any(
        "Trilha de decisões · 2 evento(s) · cadeia íntegra" in e.label
        for e in at.expander
    )
    assert any("Dra. Renata Silveira" in m and "R-REVISAO" in m for m in markdowns)


@pytest.mark.parametrize(
    ("resposta", "colecao", "trecho"),
    [
        (_RespHttp(202, {}), "info", "ainda está sendo processado"),
        (_RespHttp(404, {}), "warning", "Resultado indisponível"),
        (None, "error", "Não consegui falar com a API."),
    ],
)
def test_ui_revisao_estados_erro_e_processando(monkeypatch, resposta, colecao, trecho):
    import requests

    def fake_get(url, **kw):
        if resposta is None:
            raise requests.ConnectionError("API offline")
        return resposta

    at = _abrir_revisao(monkeypatch, get_fn=fake_get)
    assert not at.exception
    assert any(trecho in item.value for item in getattr(at, colecao))


def test_ui_revisao_decisao_aprovar_envia_post_e_exibe_sucesso(monkeypatch):
    import requests

    enviados: list[tuple[str, dict]] = []

    def fake_post(url, json=None, **kw):
        enviados.append((url, json))
        return _RespHttp(200, {"status": "aprovado"})

    monkeypatch.setattr(requests, "post", fake_post)
    at = _abrir_revisao(monkeypatch)
    assert not at.exception

    at.button(key="rv_confirmar").click().run()
    assert not at.exception
    assert enviados == [
        (
            "http://localhost:8000/documentos/DOC-REV-1/decisao",
            {"acao": "aprovar", "auditora": "Dra. Renata Silveira"},
        )
    ]
    assert any("Documento aprovado." in s.value for s in at.success)


def test_ui_revisao_decisao_redirecionar_carrega_destinos_e_envia_post(monkeypatch):
    import requests

    enviados: list[dict] = []
    monkeypatch.setattr(
        requests,
        "post",
        lambda url, json=None, **kw: (enviados.append(json), _RespHttp(200, {}))[1],
    )
    at = _abrir_revisao(monkeypatch)
    assert not at.exception

    at.radio(key="rv_acao").set_value("redirecionar").run()
    assert not at.exception
    seletor = at.selectbox(key="rv_destino")
    assert "Fila_Revisao_Humana" not in seletor.options
    assert "Farmacia_Hospitalar" in seletor.options

    seletor.select("Farmacia_Hospitalar").run()
    at.button(key="rv_confirmar").click().run()
    assert not at.exception
    assert enviados == [
        {
            "acao": "redirecionar",
            "auditora": "Dra. Renata Silveira",
            "destino": "Farmacia_Hospitalar",
        }
    ]
    assert any("Documento redirecionado." in s.value for s in at.success)


def test_ui_revisao_decisao_rejeitar_exige_motivo_e_envia_post(monkeypatch):
    import requests

    enviados: list[dict] = []
    monkeypatch.setattr(
        requests,
        "post",
        lambda url, json=None, **kw: (enviados.append(json), _RespHttp(200, {}))[1],
    )
    at = _abrir_revisao(monkeypatch)
    assert not at.exception

    at.radio(key="rv_acao").set_value("rejeitar").run()
    at.button(key="rv_confirmar").click().run()
    assert not at.exception
    assert not enviados
    assert any("Motivo da rejeição é obrigatório." in e.value for e in at.error)

    at.text_input(key="rv_motivo").input("Documento rasurado").run()
    at.button(key="rv_confirmar").click().run()
    assert not at.exception
    assert enviados == [
        {
            "acao": "rejeitar",
            "auditora": "Dra. Renata Silveira",
            "motivo": "Documento rasurado",
        }
    ]
    assert any("Documento rejeitado." in s.value for s in at.success)


def test_ui_revisao_decisao_erro_http_exibe_detalhe(monkeypatch):
    import requests

    monkeypatch.setattr(
        requests,
        "post",
        lambda url, json=None, **kw: _RespHttp(
            409, {"detail": "Documento já decidido."}
        ),
    )
    at = _abrir_revisao(monkeypatch)
    assert not at.exception

    at.button(key="rv_confirmar").click().run()
    assert not at.exception
    assert any(
        "HTTP 409" in e.value and "Documento já decidido." in e.value for e in at.error
    )


def test_ui_revisao_botao_ver_dashboard_chama_abrir_caso(monkeypatch):
    import streamlit as st

    destinos: list[str] = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinos.append(page))
    at = _abrir_revisao(monkeypatch)
    assert not at.exception

    at.button(key="rv_ver_dashboard").click().run()
    assert not at.exception
    assert destinos == ["pages/3_Dashboard.py"]
    assert at.session_state["caso_id"] == "DOC-REV-1"


def test_ui_revisao_caso_ja_decidido_bloqueia_formulario_e_mostra_resumo(monkeypatch):
    caso_decidido = _caso_revisao("DOC-DECIDIDO")
    caso_decidido["status_documento"] = "processado"
    caso_decidido["decisao_roteamento"] = {
        "destino_principal": "Farmacia_Hospitalar",
        "requer_auditoria_humana": False,
        "regra_aplicada": "R-AUDITORA",
        "justificativa_roteamento": "Destino definido pela auditora: Farmacia_Hospitalar.",
    }

    def fake_get(url, **kw):
        if url.endswith("/documentos/DOC-DECIDIDO"):
            return _RespHttp(200, caso_decidido)
        if url.endswith("/documentos/DOC-DECIDIDO/original"):
            return _RespHttp(
                200,
                content=b"Receita medica",
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        if url.endswith("/documentos/DOC-DECIDIDO/trilha"):
            return _RespHttp(200, _trilha_exemplo())
        raise AssertionError(f"URL inesperada: {url}")

    at = _abrir_revisao(monkeypatch, doc_id="DOC-DECIDIDO", get_fn=fake_get)
    assert not at.exception
    markdowns = [m.value for m in at.markdown]
    assert any("RESUMO DA DECISÃO" in m for m in markdowns)
    assert not any("POR QUE ESTÁ EM REVISÃO" in m for m in markdowns)
    assert any("já foi decidido" in i.value for i in at.info)
    assert not at.radio
    assert not any(b.key == "rv_confirmar" for b in at.button)
