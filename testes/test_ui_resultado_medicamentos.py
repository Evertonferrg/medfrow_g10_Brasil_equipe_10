"""H1.3.4 T4/T6 no Dashboard de resultado (consulta GET /documentos/{id})."""

from html.parser import HTMLParser
from pathlib import Path

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

PAGINA = str(Path(__file__).resolve().parents[1] / "ui" / "pages" / "3_Dashboard.py")


class Resp:
    def __init__(self, status, corpo=None, content=b"", headers=None):
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


class _ExtratorTabelasHTML(HTMLParser):
    """Extrai tabelas HTML (<table class="docs">) dos cards do Dashboard."""

    def __init__(self):
        super().__init__()
        self.tabelas: list[list[dict[str, str]]] = []
        self._cabecalhos: list[str] = []
        self._linhas: list[dict[str, str]] = []
        self._celulas: list[str] = []
        self._tag_celula: str | None = None
        self._texto: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._cabecalhos, self._linhas = [], []
        elif tag == "tr":
            self._celulas = []
        elif tag in ("th", "td"):
            self._tag_celula = tag
            self._texto = []

    def handle_data(self, data):
        if self._tag_celula:
            self._texto.append(data)

    def handle_endtag(self, tag):
        if tag == self._tag_celula:
            valor = "".join(self._texto).strip()
            if tag == "th":
                self._cabecalhos.append(valor)
            else:
                self._celulas.append(valor)
            self._tag_celula = None
        elif tag == "tr" and self._celulas and self._cabecalhos:
            self._linhas.append(
                dict(zip(self._cabecalhos, self._celulas, strict=False))
            )
        elif tag == "table" and self._linhas:
            self.tabelas.append(self._linhas)


def resultado(tipo="Receituário Médico", **dados):
    return {
        "status": "processado",
        "documento_id": "DOC-1",
        "problemas": [],
        "classificacao": {
            "tipo_documento": tipo,
            "especialidade": "Clínica Geral",
            "nivel_prioridade": "Rotina",
            "score_confianca_classificacao": 0.93,
        },
        "decisao_roteamento": {
            "destino_principal": "Farmacia_Hospitalar",
            "requer_auditoria_humana": False,
            "justificativa_roteamento": "ok",
        },
        "dados_extraidos": dados,
    }


@pytest.fixture(autouse=True)
def api(monkeypatch):
    st.cache_data.clear()
    monkeypatch.delenv("API_URL", raising=False)
    reg = {"resposta": resultado()}

    def falso_get(url, **kw):
        if url.endswith("/original"):
            return Resp(404)
        if url.rstrip("/").endswith("/documentos"):
            return Resp(200, [])
        return Resp(200, reg["resposta"])

    monkeypatch.setattr(requests, "get", falso_get)
    return reg


def buscar(doc_id="DOC-1"):
    at = AppTest.from_file(PAGINA, default_timeout=30)
    at.session_state["caso_id"] = doc_id
    return at.run()


def tabelas(at):
    parser = _ExtratorTabelasHTML()
    for m in at.markdown:
        if "<table" in m.value:
            parser.feed(m.value)
    return parser.tabelas


def test_a_pagina_da_equipe_continua_mostrando_tipo_e_destino(api):
    at = buscar()
    assert not at.exception
    assert {m.label for m in at.metric} >= {
        "Tipo do documento",
        "Especialidade provável",
        "Prioridade",
        "Confiança",
    }
    assert any(
        "DESTINO" in m.value and "Farmacia_Hospitalar" in m.value for m in at.markdown
    )


def test_tabela_de_medicamentos_tem_uma_linha_por_item(api):
    api["resposta"] = resultado(
        medicamentos=[
            {
                "nome": "Amoxicilina",
                "dose": "500mg",
                "via": "via oral",
                "frequencia": "8/8h",
                "duracao": "7 dias",
            },
            {"nome": "Dipirona", "dose": "1g"},
            {"nome": "Omeprazol", "dose": "20mg"},
        ]
    )
    at = buscar()
    assert not at.exception
    linhas = tabelas(at)[0]
    assert [linha["Medicamento"] for linha in linhas] == [
        "Amoxicilina",
        "Dipirona",
        "Omeprazol",
    ]
    assert linhas[0] == {
        "Medicamento": "Amoxicilina",
        "Dose": "500mg",
        "Via": "via oral",
        "Frequência": "8/8h",
        "Duração": "7 dias",
    }
    assert linhas[1]["Via"] == "—" and linhas[1]["Duração"] == "—"


def test_medicamento_sem_dose_mostra_selo_sem_dose(api):
    api["resposta"] = resultado(medicamentos=[{"nome": "Amoxicilina", "dose": None}])
    at = buscar()
    assert not at.exception
    assert tabelas(at)[0][0]["Dose"] == "sem dose"


def test_receita_sem_medicamentos_avisa(api):
    at = buscar()
    assert not at.exception
    assert not tabelas(at)
    assert any("Nenhum medicamento" in c.value for c in at.caption)


def test_laudo_sem_medicamentos_nao_mostra_a_secao(api):
    api["resposta"] = resultado(tipo="Laudo de Exame de Imagem")
    at = buscar()
    assert not at.exception
    assert not any("MEDICAMENTOS" in m.value for m in at.markdown)
