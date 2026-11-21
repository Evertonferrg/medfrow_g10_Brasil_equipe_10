from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from ui.componentes.fila import minutos_de_espera, texto_dose_destacada, texto_espera

PAGINA_FILA = str(
    Path(__file__).resolve().parents[1] / "ui" / "pages" / "6_Fila_de_Revisao.py"
)


class _RespFila:
    def __init__(self, status: int = 200, corpo=None):
        self.status_code = status
        self._corpo = corpo

    def json(self):
        return self._corpo

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _caso_exemplo(
    doc_id: str = "DOC-FILA-1",
    *,
    tipo: str = "Receituário Médico",
    prioridade: str = "Urgente",
    motivos: list[str] | None = None,
    destaques_dose: list[dict] | None = None,
) -> dict:
    chegada = (datetime.now(UTC) - timedelta(minutes=25)).isoformat()
    return {
        "documento_id": doc_id,
        "tipo": tipo,
        "prioridade": prioridade,
        "chegada_em": chegada,
        "motivos": motivos or ["Confiança abaixo do limite (0.65)."],
        "destaques_dose": destaques_dose or [],
    }


def test_minutos_de_espera():
    agora = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
    assert minutos_de_espera((agora - timedelta(minutes=45)).isoformat(), agora) == 45
    assert minutos_de_espera((agora + timedelta(minutes=5)).isoformat(), agora) == 0


def test_texto_espera_e_destaque_com_texto():
    assert texto_espera(75) == "1 h 15 min" and texto_espera(8) == "8 min"
    assert "FORA DA FAIXA" in texto_dose_destacada(
        {"medicamento": "Morfina", "dose": "500 mg"}
    )


def test_fila_vazia_exibe_mensagem_informativa(monkeypatch):
    monkeypatch.delenv("API_URL", raising=False)
    monkeypatch.setattr(requests, "get", lambda url, **kw: _RespFila(200, []))

    at = AppTest.from_file(PAGINA_FILA, default_timeout=30).run()
    assert not at.exception
    assert any("Nenhum documento aguardando revisão." in i.value for i in at.info)


def test_fila_erro_de_rede_exibe_mensagem_amigavel(monkeypatch):
    monkeypatch.delenv("API_URL", raising=False)

    def erro_rede(url, **kw):
        raise requests.ConnectionError("API indisponível")

    monkeypatch.setattr(requests, "get", erro_rede)

    at = AppTest.from_file(PAGINA_FILA, default_timeout=30).run()
    assert not at.exception
    assert any("Não foi possível carregar a fila." in e.value for e in at.error)


def test_fila_lista_casos_com_motivos_e_destaque_de_dose(monkeypatch):
    monkeypatch.delenv("API_URL", raising=False)
    casos = [
        _caso_exemplo(
            "DOC-FILA-1",
            tipo="Receituário Médico",
            prioridade="Urgente",
            motivos=["Dose acima da faixa terapêutica."],
            destaques_dose=[{"medicamento": "Morfina", "dose": "500 mg"}],
        ),
        _caso_exemplo(
            "DOC-FILA-2",
            tipo="Laudo de Exame",
            prioridade="Rotina",
            motivos=["CRM ausente no documento."],
        ),
    ]
    monkeypatch.setattr(requests, "get", lambda url, **kw: _RespFila(200, casos))

    at = AppTest.from_file(PAGINA_FILA, default_timeout=30).run()
    assert not at.exception
    assert any("2 documento(s) pendente(s)" in c.value for c in at.caption)
    markdowns = [m.value for m in at.markdown]
    assert any(
        "DOC-FILA-1" in m and "Receituário Médico" in m and "Urgente" in m
        for m in markdowns
    )
    assert any("Dose acima da faixa terapêutica." in m for m in markdowns)
    assert any("DOSE FORA DA FAIXA: Morfina 500 mg" in m for m in markdowns)
    assert any("DOC-FILA-2" in m and "Laudo de Exame" in m for m in markdowns)
    assert any("CRM ausente no documento." in m for m in markdowns)


def test_fila_botao_revisar_agora_chama_abrir_revisao(monkeypatch):
    monkeypatch.delenv("API_URL", raising=False)
    monkeypatch.setattr(
        requests, "get", lambda url, **kw: _RespFila(200, [_caso_exemplo("DOC-FILA-1")])
    )
    destinos: list[str] = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinos.append(page))

    at = AppTest.from_file(PAGINA_FILA, default_timeout=30).run()
    assert not at.exception

    at.button(key="revisar_DOC-FILA-1").click().run()
    assert not at.exception
    assert destinos == ["pages/13_UI_Revisao_de_Caso.py"]
    assert at.session_state["caso_id"] == "DOC-FILA-1"
    assert at.session_state["_id_para_url"] == "DOC-FILA-1"


def test_fila_botao_abrir_caso_chama_abrir_caso(monkeypatch):
    monkeypatch.delenv("API_URL", raising=False)
    monkeypatch.setattr(
        requests, "get", lambda url, **kw: _RespFila(200, [_caso_exemplo("DOC-FILA-1")])
    )
    destinos: list[str] = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinos.append(page))

    at = AppTest.from_file(PAGINA_FILA, default_timeout=30).run()
    assert not at.exception

    at.button(key="abrir_DOC-FILA-1").click().run()
    assert not at.exception
    assert destinos == ["pages/3_Dashboard.py"]
    assert at.session_state["caso_id"] == "DOC-FILA-1"
    assert at.query_params["id"] == "DOC-FILA-1"
