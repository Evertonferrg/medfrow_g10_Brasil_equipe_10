"""H1.3.1 T4 — Dados do paciente: nome, idade e data de nascimento.

Todos os documentos são sintéticos (LGPD). O LLM é substituído por extratores falsos,
então nada aqui chama a rede.
"""

import sys
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

from app.grafo import triar
from app.schemas import Medico, Paciente
from testes.conftest import LAUDO_TEP, RECEITA, cliente_com, extracao, extrator_fixo

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "ui"))  # igual ao Streamlit em execução (pasta do script)
from ui.componentes.paciente import resumo_paciente

PAGINA_RESULTADO = str(RAIZ / "ui" / "pages" / "2_Triagem.py")

MEDICO = "Solicitante: Dra. Renata Silveira CRM-SP 145892."  # bate com o médico de extracao()


def laudo(trecho_paciente: str) -> str:
    return f"LAUDO sintetico. {trecho_paciente} {MEDICO} Tomografia de torax."


def corpo(texto: str, doc_id: str = "PAC-0001") -> dict:
    return {
        "documento_id": doc_id,
        "tipo_arquivo": "TEXTO",
        "documento_texto": texto,
        "canal_origem": "Pronto_Socorro",
    }


# ---- critério 1: laudo de exemplo do edital ----
def test_laudo_do_edital_devolve_nome_e_idade_pelo_grafo():
    s = triar(LAUDO_TEP, extrator_fixo(extracao()))
    assert s["extracao"].paciente.nome == "Carlos Eduardo Mendes"
    assert s["extracao"].paciente.idade == 52


def test_laudo_do_edital_devolve_nome_e_idade_pela_api():
    c = cliente_com(extrator_fixo(extracao()))
    j = c.post("/triagem?aguardar=true", json=corpo(LAUDO_TEP)).json()
    assert j["dados_extraidos"]["paciente"] == {
        "nome": "Carlos Eduardo Mendes",
        "idade": 52,
        "data_nascimento": None,
    }


# ---- critério 2: data de nascimento preservada como está escrita ----
@pytest.mark.parametrize(
    "data", ["03/04/1985", "3 de abril de 1985", "1985-04-03", "03.04.85"]
)
def test_data_de_nascimento_e_preservada_como_escrita(data):
    ext = extracao(
        paciente=Paciente(nome="Maria Souza", idade=None, data_nascimento=data)
    )
    texto = laudo(f"Paciente: Maria Souza, nascida em {data}.")
    c = cliente_com(extrator_fixo(ext))
    j = c.post("/triagem?aguardar=true", json=corpo(texto)).json()
    paciente = j["dados_extraidos"]["paciente"]
    assert paciente["data_nascimento"] == data  # nenhum reformatamento
    assert paciente["idade"] is None  # e a idade não foi inventada


# ---- nome acentuado sai idêntico ----
@pytest.mark.parametrize(
    "nome", ["José Antônio Conceição", "Ângela Müller Peçanha", "Zoé d'Ávila"]
)
def test_nome_acentuado_sai_identico_inclusive_depois_de_gravado(nome):
    ext = extracao(paciente=Paciente(nome=nome, idade=61))
    c = cliente_com(extrator_fixo(ext))
    agora = c.post(
        "/triagem?aguardar=true", json=corpo(laudo(f"Paciente: {nome}, 61 anos."))
    )
    assert agora.json()["dados_extraidos"]["paciente"]["nome"] == nome
    assert not any(
        "Nome" in p for p in agora.json()["problemas"]
    )  # não foi tratado como inventado
    consulta = c.get("/triagem/PAC-0001").json()  # leitura do que foi arquivado
    assert consulta["dados_extraidos"]["paciente"]["nome"] == nome


# ---- proteção: o nome precisa estar no documento ----
def test_nome_que_nao_esta_no_texto_vai_para_revisao():
    ext = extracao(paciente=Paciente(nome="Roberto Alves Lima", idade=40))
    s = triar(laudo("Paciente: Carlos Eduardo Mendes, 52 anos."), extrator_fixo(ext))
    assert s["destino"] == "Fila_Revisao_Humana"
    assert any("Roberto Alves Lima" in p for p in s["problemas"])


# ---- o prompt carrega as regras que o teste do LLM real vai cobrar ----
@pytest.mark.xfail(
    reason="aguardando o PR do llm.py (divisão do prompt): regras do paciente ainda não entraram",
    strict=False,
)
def test_prompt_manda_copiar_o_nome_e_proibe_calcular_a_idade():
    # import app.llm as llm
    from app import llm

    prompts = [
        v.lower()
        for v in vars(llm).values()
        if isinstance(v, str) and "<documento>" in v
    ]
    assert any("literalmente" in p and "nunca calcule a idade" in p for p in prompts)


# ---- bloco da tela ----
def test_resumo_mostra_traco_quando_falta_dado():
    assert resumo_paciente(None) == {
        "Nome": "—",
        "Idade": "—",
        "Data de nascimento": "—",
    }
    assert resumo_paciente({"nome": "Maria Souza", "idade": 34})["Idade"] == "34 anos"


def test_bloco_paciente_exibe_nome_e_data_como_texto_puro():
    dados = {
        "paciente": {
            "nome": "José Antônio Conceição",
            "idade": None,
            "data_nascimento": "3 de abril de 1985",
        }
    }
    script = (
        f"import sys; sys.path.insert(0, {str(RAIZ / 'ui')!r})\n"
        "from componentes.paciente import bloco_paciente\n"
        f"bloco_paciente({dados!r})\n"
    )
    at = AppTest.from_string(script, default_timeout=10).run()
    assert not at.exception
    assert [t.value for t in at.text_input] == [
        "José Antônio Conceição",
        "—",
        "3 de abril de 1985",
    ]
    assert all(t.disabled for t in at.text_input)


# ---- regressão: a 2ª busca na mesma sessão precisa trocar paciente e médico ----
# (Bug 1: os campos mostravam o documento da consulta anterior, porque o valor
# vinha só de value= e o session_state do widget antigo continuava valendo.)


class _Resp:
    """Resposta falsa do GET /documentos/{id} (mesmo formato das outras telas)."""

    def __init__(self, corpo: dict):
        self.status_code = 200
        self.text = ""
        self._corpo = corpo

    def json(self) -> dict:
        return self._corpo


def _resposta_da_api(texto: str, ext, doc_id: str) -> dict:
    """Gera o JSON da consulta montando pelo próprio grafo (extrator falso, sem rede)."""
    return triar(texto, extrator_fixo(ext), documento_id=doc_id)["resultado"]


def test_segunda_busca_na_mesma_sessao_mostra_o_documento_atual(monkeypatch):
    ext_receita = extracao(
        paciente=Paciente(nome="Maria Souza", idade=40),
        medico_solicitante=Medico(nome="Dr. Paulo Lima", crm="CRM 99887 SP"),
    )
    payloads = {
        "DOC-A": _resposta_da_api(LAUDO_TEP, extracao(), "DOC-A"),
        "DOC-B": _resposta_da_api(RECEITA, ext_receita, "DOC-B"),
    }
    monkeypatch.setattr(
        requests, "get", lambda url, **kw: _Resp(payloads[url.rsplit("/", 1)[-1]])
    )

    # o mesmo AppTest = a mesma sessão do Streamlit, como no navegador
    at = AppTest.from_file(PAGINA_RESULTADO, default_timeout=30).run()

    # 1ª busca: laudo de TEP (Carlos Eduardo Mendes / Dra. Renata Silveira)
    at.text_input[0].set_value("DOC-A")
    at.button[0].click().run()
    assert not at.exception
    assert at.text_input(key="paciente_Nome").value == "Carlos Eduardo Mendes"
    assert at.text_input(key="paciente_Idade").value == "52 anos"
    assert at.text_input(key="medico_nome").value == "Dra. Renata Silveira"
    assert at.text_input(key="medico_crm").value == "145892-SP"

    # 2ª busca: os campos precisam trocar por completo (era aqui que travava)
    at.text_input[0].set_value("DOC-B")
    at.button[0].click().run()
    assert not at.exception
    assert at.text_input(key="paciente_Nome").value == "Maria Souza"
    assert at.text_input(key="paciente_Idade").value == "40 anos"
    assert at.text_input(key="medico_nome").value == "Dr. Paulo Lima"
    assert at.text_input(key="medico_crm").value == "99887-SP"
