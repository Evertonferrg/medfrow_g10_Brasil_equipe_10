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
