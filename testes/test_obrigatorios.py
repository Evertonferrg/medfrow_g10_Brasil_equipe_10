from app.validacao_obrigatorios import campos_faltantes

R = "Receituário Médico"
G = "Guia de Solicitação de Procedimento"


def test_receita_sem_paciente_e_dose():
    dados = {"medicamento": "Dipirona", "crm": "123456"}
    assert sorted(campos_faltantes(R, dados)) == [
        "campo faltante: dose",
        "campo faltante: nome_paciente",
    ]


def test_guia_sem_procedimento():
    dados = {"medico_solicitante": "Dra. Ana"}
    assert campos_faltantes(G, dados) == ["campo faltante: procedimento"]


def test_documento_completo():
    dados = {"nome_paciente": "João", "medicamento": "X", "dose": "5mg", "crm": "1"}
    assert campos_faltantes(R, dados) == []
