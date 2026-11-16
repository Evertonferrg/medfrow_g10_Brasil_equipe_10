"""H6.4.1 — Testes do histórico e restauração de versões das regras."""

import pytest

from app.regras import RegrasConfig, ServicoRegras, servico_regras


def criar_regras_iniciais():
    """Cria uma configuração inicial identificável para os testes."""
    return RegrasConfig(
        limite_confianca=0.80,
        versao="v1",
        atualizado_por="Sistema",
        atualizado_em="2026-11-16T10:00:00+00:00",
    )


def test_salvar_regras_registra_versao_no_historico():
    """A configuração inicial deve ser registrada com autor e data."""
    srv = ServicoRegras()
    regras = criar_regras_iniciais()

    srv.salvar_regras(regras)

    historico = srv.listar_versoes()

    assert len(historico) == 1
    assert historico[0]["versao"] == "v1"
    assert historico[0]["autor"] == "Sistema"
    assert historico[0]["data"] is not None
    assert historico[0]["configuracao"]["limite_confianca"] == 0.80


def test_alteracao_registra_nova_versao_e_diferencas():
    """A alteração deve registrar autor, data e diferenças campo a campo."""
    srv = ServicoRegras()
    srv.salvar_regras(criar_regras_iniciais())

    nova = srv.atualizar_limite(
        novo_limite=0.90,
        auditora="Dra. Ana",
    )

    historico = srv.listar_versoes()

    assert nova.versao == "v2"
    assert nova.limite_confianca == 0.90
    assert nova.atualizado_por == "Dra. Ana"
    assert nova.atualizado_em is not None

    versao_nova = next(item for item in historico if item["versao"] == "v2")

    assert versao_nova["autor"] == "Dra. Ana"
    assert versao_nova["data"] is not None
    assert "limite_confianca" in versao_nova["diferencas"]
    assert versao_nova["diferencas"]["limite_confianca"]["anterior"] == 0.80
    assert versao_nova["diferencas"]["limite_confianca"]["novo"] == 0.90


def test_listar_versoes_ordena_da_mais_recente_para_mais_antiga():
    """O histórico deve ser apresentado em ordem decrescente."""
    srv = ServicoRegras()
    srv.salvar_regras(criar_regras_iniciais())

    srv.atualizar_limite(0.90, auditora="Auditora 1")
    srv.atualizar_limite(0.95, auditora="Auditora 2")

    historico = srv.listar_versoes()

    assert [item["versao"] for item in historico] == [
        "v3",
        "v2",
        "v1",
    ]


def test_restaurar_versao_cria_nova_versao_sem_apagar_historico():
    """Restaurar uma versão antiga não deve sobrescrever o histórico."""
    srv = ServicoRegras()
    srv.salvar_regras(criar_regras_iniciais())

    srv.atualizar_limite(0.90, auditora="Auditora 1")

    restaurada = srv.restaurar_versao(
        versao="v1",
        auditora="Auditora Restauradora",
    )

    historico = srv.listar_versoes()

    assert restaurada.versao == "v3"
    assert restaurada.limite_confianca == 0.80
    assert restaurada.atualizado_por == "Auditora Restauradora"

    # As versões anteriores continuam preservadas.
    assert [item["versao"] for item in historico] == [
        "v3",
        "v2",
        "v1",
    ]

    # A versão restaurada também deve estar registrada.
    registro_restaurado = historico[0]

    assert registro_restaurado["autor"] == "Auditora Restauradora"
    assert registro_restaurado["configuracao"]["limite_confianca"] == 0.80


def test_restaurar_versao_inexistente_gera_erro():
    """Uma versão que não existe deve gerar ValueError."""
    srv = ServicoRegras()
    srv.salvar_regras(criar_regras_iniciais())

    with pytest.raises(ValueError, match="não encontrada"):
        srv.restaurar_versao("v99")


def test_api_lista_historico_de_versoes(cliente):
    """GET /regras/versoes deve retornar o histórico."""
    srv = servico_regras()
    srv.salvar_regras(criar_regras_iniciais())

    resposta = cliente.get("/regras/versoes")

    assert resposta.status_code == 200
    dados = resposta.json()

    assert "versoes" in dados
    assert any(item["versao"] == "v1" for item in dados["versoes"])


def test_api_restaura_versao_historica(cliente):
    """POST /regras/restaurar/{versao} deve restaurar e criar nova versão."""
    srv = servico_regras()
    srv.salvar_regras(criar_regras_iniciais())
    srv.atualizar_limite(0.90, auditora="Auditora 1")

    resposta = cliente.post(
        "/regras/restaurar/v1",
        json={"auditora": "Auditora Restauradora"},
    )

    assert resposta.status_code == 200

    dados = resposta.json()

    assert dados["versao"] == "v3"
    assert dados["limite_confianca"] == 0.80
    assert dados["atualizado_por"] == "Auditora Restauradora"

    historico = cliente.get("/regras/versoes").json()["versoes"]

    assert [item["versao"] for item in historico] == [
        "v3",
        "v2",
        "v1",
    ]


def test_api_restauracao_versao_inexistente_retorna_422(cliente):
    """POST para uma versão inexistente deve retornar HTTP 422."""
    srv = servico_regras()
    srv.salvar_regras(criar_regras_iniciais())

    resposta = cliente.post("/regras/restaurar/v99")

    assert resposta.status_code == 422
    assert "não encontrada" in resposta.json()["detail"]
