from app.verificacoes.alta_vigilancia import (
    carregar_config,
    interpretar_dose,
    verificar_alto_risco,
)

CFG = carregar_config()  # faixas FICTÍCIAS (ver aviso no JSON)


def test_interpretar_dose():
    assert interpretar_dose("500 mg") == (500.0, "mg")
    assert interpretar_dose("10 UI") == (10.0, "ui")
    assert interpretar_dose("2,5mg") == (2.5, "mg")
    assert interpretar_dose("a critério médico") is None


def test_receita_com_morfina_vai_a_revisao():
    a = verificar_alto_risco([{"nome": "Morfina", "dose": "10 mg"}], CFG)
    assert len(a) == 1 and a[0].classe == "opioides" and not a[0].fora_da_faixa
    assert "alto risco" in a[0].texto.lower()


def test_dose_acima_da_faixa_ficticia_cita_a_dose():
    a = verificar_alto_risco([{"nome": "Morfina", "dose": "500 mg"}], CFG)
    assert a[0].fora_da_faixa and "500 mg" in a[0].texto


def test_unidade_diferente_da_configurada_tambem_vai_a_revisao():
    a = verificar_alto_risco([{"nome": "Morfina", "dose": "5 g"}], CFG)
    assert a[0].fora_da_faixa


def test_medicamento_comum_nao_e_alto_risco():
    assert verificar_alto_risco([{"nome": "Dipirona", "dose": "500 mg"}], CFG) == []


def test_acento_e_caixa_nao_atrapalham():
    assert verificar_alto_risco([{"nome": "METOTREXATO 2,5mg", "dose": "2,5 mg"}], CFG)
