"""H6.3.1 T6 — Testes de destinos configuráveis e regras de roteamento editáveis."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import roteamento as rt
from app.api.main import app
from app.modelos import Destino
from app.regras import (
    DESTINOS_OFICIAIS,
    RegrasConfig,
    servico_regras,
)
from app.revisao import obter_destinos_redirecionaveis


@pytest.fixture
def cliente():
    return TestClient(app)


@pytest.fixture(autouse=True)
def limpar_regras(monkeypatch, tmp_path):
    """Garante isolamento dos testes de regras usando pasta temporária."""
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    # Reseta a instância global do ServicoRegras
    from app import regras

    regras._instancia_servico = None
    servico = regras.servico_regras()
    servico.salvar_regras(
        RegrasConfig(
            destinos=list(DESTINOS_OFICIAIS),
            regras_roteamento=[],
            versao="v1",
        )
    )
    yield servico
    regras._instancia_servico = None


# -----------------------------------------------------------------------------
# Cenário 1: com a regra "CID começa com C → Oncologia", laudo de rotina vai para Oncologia
# -----------------------------------------------------------------------------
def test_laudo_neoplasia_com_regra_cid_c_vai_para_oncologia(cliente):
    """Critério 1: Dado um destino criado com a regra 'CID começa com C', laudo vai para Oncologia."""
    # 1. Cria o destino Oncologia via API
    r_dest = cliente.post(
        "/regras/destinos", json={"nome": "Oncologia", "auditora": "Auditora"}
    )
    assert r_dest.status_code == 200
    assert "Oncologia" in r_dest.json()["destinos"]

    # 2. Cria a regra de roteamento
    r_regra = cliente.post(
        "/regras/roteamento",
        json={
            "id": "R-ONCOLOGIA",
            "tipo_condicao": "cid_comeca_com",
            "valor": "C",
            "destino": "Oncologia",
            "auditora": "Auditora",
        },
    )
    assert r_regra.status_code == 200

    # 3. Laudo de neoplasia (CID C34.9) com prioridade Rotina
    estado_laudo = {
        "tipo_documento": "Laudo de Exame de Imagem",
        "prioridade": "Rotina",
        "score": 0.95,
        "cid": "C34.9",
        "problemas": [],
    }

    destino = rt.decidir_destino(estado_laudo)
    assert destino == "Oncologia"

    decisao = rt.criar_decisao_roteamento(estado_laudo)
    assert decisao.destino_principal == "Oncologia"
    assert decisao.regra_aplicada == "R-ONCOLOGIA"
    assert "Oncologia" in decisao.justificativa_roteamento


# -----------------------------------------------------------------------------
# Cenário 2: o mesmo laudo marcado Urgente vai para a emergência
# -----------------------------------------------------------------------------
def test_mesmo_laudo_marcado_urgente_vai_para_emergencia(cliente):
    """Critério e T6: urgência tem precedência sobre regras configuráveis."""
    # Cadastra Oncologia e a regra CID C -> Oncologia
    cliente.post("/regras/destinos", json={"nome": "Oncologia"})
    cliente.post(
        "/regras/roteamento",
        json={
            "id": "R-ONCOLOGIA",
            "tipo_condicao": "cid_comeca_com",
            "valor": "C",
            "destino": "Oncologia",
        },
    )

    # Mesmo laudo, porém com prioridade Urgente
    estado_urgente = {
        "tipo_documento": "Laudo de Exame de Imagem",
        "prioridade": "Urgente",
        "score": 0.95,
        "cid": "C34.9",
        "problemas": [],
    }

    destino = rt.decidir_destino(estado_urgente)
    assert destino == Destino.FILA_EMERGENCIA_MEDICA

    decisao = rt.criar_decisao_roteamento(estado_urgente)
    assert decisao.destino_principal == Destino.FILA_EMERGENCIA_MEDICA
    assert decisao.regra_aplicada == "R-URGENCIA"


# -----------------------------------------------------------------------------
# Cenário 3: regra com destino inexistente devolve 422
# -----------------------------------------------------------------------------
def test_regra_com_destino_inexistente_devolve_422(cliente):
    """T6: regra para destino não cadastrado em RegrasConfig devolve 422."""
    resp = cliente.post(
        "/regras/roteamento",
        json={
            "tipo_condicao": "cid_comeca_com",
            "valor": "C",
            "destino": "Destino_Inexistente_Hospitalar",
        },
    )
    assert resp.status_code == 422
    assert (
        "não existe" in resp.json()["detail"].lower()
        or "inexistente" in resp.json()["detail"].lower()
    )


# -----------------------------------------------------------------------------
# Cenário 4: Novo destino aparece na lista de destinos da auditora (H4.4.4 / T5)
# -----------------------------------------------------------------------------
def test_novo_destino_aparece_na_lista_da_auditora(cliente):
    """Critério 2 e T5: o novo destino aparece no seletor da auditora."""
    # Inicialmente, Oncologia não está na lista
    destinos_iniciais = obter_destinos_redirecionaveis()
    assert "Oncologia" not in destinos_iniciais

    # Cria o destino Oncologia
    cliente.post("/regras/destinos", json={"nome": "Oncologia"})

    # Verifica pela função e pela rota
    destinos_atualizados = obter_destinos_redirecionaveis()
    assert "Oncologia" in destinos_atualizados

    resp = cliente.get("/regras/destinos")
    assert resp.status_code == 200
    assert "Oncologia" in resp.json()["destinos"]


# -----------------------------------------------------------------------------
# Cenário 5: Os cinco destinos oficiais do edital são fixos e não podem ser removidos (T1)
# -----------------------------------------------------------------------------
def test_destinos_oficiais_do_edital_sao_protegidos():
    """T1: os cinco destinos oficiais do edital não podem ser removidos."""
    servico = servico_regras()

    # Tentativa de remover destino oficial via método do serviço
    with pytest.raises(ValueError, match="oficiais"):
        servico.remover_destino("Farmacia_Hospitalar")

    # Tentativa de validar RegrasConfig sem um dos destinos oficiais
    destinos_incompletos = [
        "Auditoria_Autorizacoes",
        "Prontuario_Eletronico",
        "Fila_Emergencia_Medica",
        "Fila_Revisao_Humana",
    ]  # falta Farmacia_Hospitalar
    with pytest.raises(ValueError, match="oficiais"):
        RegrasConfig(destinos=destinos_incompletos)


# -----------------------------------------------------------------------------
# Cenário 6: Condição restrita ao conjunto fechado: rejeita expressão livre (T2)
# -----------------------------------------------------------------------------
def test_condicao_conjunto_fechado_rejeita_expressao_livre(cliente):
    """T2: nunca executar expressão livre digitada pelo usuário."""
    # Tentativa de passar condição arbitrária / expressão livre
    resp = cliente.post(
        "/regras/roteamento",
        json={
            "tipo_condicao": "expressao_livre_eval(documento.texto)",
            "valor": "True",
            "destino": "Farmacia_Hospitalar",
        },
    )
    assert resp.status_code == 422


# -----------------------------------------------------------------------------
# Cenário 7: Regra por tipo de documento configurável (T2 / T3)
# -----------------------------------------------------------------------------
def test_regra_por_tipo_de_documento_configuravel(cliente):
    """T2 e T3: condição 'tipo_documento_igual' funciona conforme esperado."""
    cliente.post("/regras/destinos", json={"nome": "Laboratorio_Especial"})
    cliente.post(
        "/regras/roteamento",
        json={
            "id": "R-LAB-ESP",
            "tipo_condicao": "tipo_documento_igual",
            "valor": "Laudo Laboratorial",
            "destino": "Laboratorio_Especial",
        },
    )

    estado_lab = {
        "tipo_documento": "Laudo Laboratorial",
        "prioridade": "Rotina",
        "score": 0.90,
        "problemas": [],
    }

    destino = rt.decidir_destino(estado_lab)
    assert destino == "Laboratorio_Especial"


# -----------------------------------------------------------------------------
# Cenário 8: Revisão humana tem precedência sobre regra configurada (T3)
# -----------------------------------------------------------------------------
def test_revisao_humana_tem_precedencia_sobre_regra_configurada(cliente):
    """T3: pendência ou score baixo vai para Fila_Revisao_Humana, mesmo com regra casando."""
    cliente.post("/regras/destinos", json={"nome": "Oncologia"})
    cliente.post(
        "/regras/roteamento",
        json={
            "id": "R-ONCOLOGIA",
            "tipo_condicao": "cid_comeca_com",
            "valor": "C",
            "destino": "Oncologia",
        },
    )

    # Score baixo (< 0.80) força revisão
    estado_com_duvida = {
        "tipo_documento": "Laudo de Exame de Imagem",
        "prioridade": "Rotina",
        "score": 0.65,
        "cid": "C34.9",
        "problemas": ["score baixo"],
    }

    destino = rt.decidir_destino(estado_com_duvida)
    assert destino == Destino.FILA_REVISAO_HUMANA
