import pytest

from ui.componentes.prioridade import etiqueta_prioridade


@pytest.mark.parametrize("nivel,cor,emoji", [("Urgente", "red", "🔴"), ("Prioritário", "orange", "🟠"),
                                              ("Rotina", "green", "🟢")])
def test_cor_texto_e_emoji(nivel, cor, emoji):
    e = etiqueta_prioridade(nivel)
    assert cor in e and emoji in e and nivel in e


def test_nivel_desconhecido_ou_vazio_nao_quebra():
    assert "Sem prioridade" in etiqueta_prioridade(None)
    assert "gray" in etiqueta_prioridade("Outro")
