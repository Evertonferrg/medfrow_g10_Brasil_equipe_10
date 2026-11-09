from datetime import date

from pydantic import BaseModel

from app.verificacoes.consistencia import (
    ParecerCID,
    conferir_cid_diagnostico,
    conferir_idade,
    converter_marcacao_crm,
    verificar_consistencia,
)

TABELA = {"S72.0": "Fratura do colo do fêmur", "I26": "Embolia pulmonar"}
HOJE = date(2026, 11, 6)


class FakeLLM:
    def __init__(self, corresponde, motivo=""):
        self.parecer = ParecerCID(corresponde=corresponde, motivo=motivo)
        self.prompts = []

    def estruturar(self, prompt, schema: type[BaseModel]):
        self.prompts.append(prompt)
        return self.parecer


def test_idade_30_com_nascimento_1950_gera_motivo():
    m = conferir_idade(30, "1950-03-10", hoje=HOJE)
    assert m and "30" in m and "1950" in m


def test_idade_compativel_ou_com_1_ano_de_diferenca_passa():
    assert conferir_idade(76, "1950-03-10", hoje=HOJE) is None
    assert conferir_idade(75, "1950-03-10", hoje=HOJE) is None  # tolerância de 1 ano


def test_idade_usa_data_do_documento_e_nao_confere_sem_os_dois():
    assert (
        conferir_idade(30, "1996-01-01", data_documento="2026-06-01", hoje=HOJE) is None
    )
    assert conferir_idade(30, None, hoje=HOJE) is None
    assert conferir_idade(None, "1950-01-01", hoje=HOJE) is None


def test_cid_de_fratura_com_diagnostico_de_tep_gera_motivo():
    llm = FakeLLM(False, "o código descreve fratura, não embolia pulmonar")
    m = conferir_cid_diagnostico("S72.0", "Tromboembolismo pulmonar", llm, TABELA)
    assert m and "S72.0" in m and "\n" not in m
    assert (
        "Fratura do colo do fêmur" in llm.prompts[0]
    )  # descrição oficial vai no prompt


def test_cid_coerente_passa():
    assert (
        conferir_cid_diagnostico("I26", "Embolia pulmonar", FakeLLM(True), TABELA)
        is None
    )


def test_crm_invalido_gera_motivo():
    assert converter_marcacao_crm(False) == "CRM inválido"
    assert converter_marcacao_crm(True) is None


def test_cada_motivo_e_uma_frase_e_todos_aparecem():
    dados = {
        "idade": 30,
        "data_nascimento": "1950-01-01",
        "cid": "S72.0",
        "diagnostico": "TEP",
        "crm_valido": False,
    }
    motivos = verificar_consistencia(
        dados, FakeLLM(False, "incompatível\ncom TEP"), TABELA, HOJE
    )
    assert len(motivos) == 3
    assert all(isinstance(m, str) and "\n" not in m for m in motivos)
