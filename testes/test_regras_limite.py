"""H6.1.1 T5 — Testes para ajuste do limite de confiança.

Cenários cobertos:
1. Com o limite alterado para 0.90, um documento novo com score 0.85 vai à revisão humana.
2. Documentos já processados mantêm o destino original após a alteração do limite.
3. Requisição de alteração com limite 0.40 devolve HTTP 422 (Unprocessable Entity).
4. Limites de 0.50 a 0.99 são aceitos e criam nova versão (H6.4.1).
5. Validação do modelo RegrasConfig para limites fora do intervalo [0.50, 0.99].
6. Gravação da versão de regras (versao_regras) em cada ResultadoTriagem.
"""

import pytest
from pydantic import ValidationError

from app.modelos import Destino
from app.regras import RegrasConfig, servico_regras
from app.schemas import (
    Extracao,
    Medicamento,
    MedicoSolicitante,
    Paciente,
    ResultadoTriagem,
)
from app.servico import processar
from testes.conftest import extrator_fixo


# ---------------------------------------------------------------------------
# Cenário 3 & 4: Validação do limite e HTTP 422
# ---------------------------------------------------------------------------
def test_put_regras_limite_invalido_devolve_422(cliente):
    """Valor 0.40 devolve 422 por estar abaixo do mínimo permitido (0.50)."""
    resp = cliente.put("/regras/limite", json={"limite_confianca": 0.40})
    assert resp.status_code == 422

    # Acima do máximo permitido (0.99) também deve devolver 422
    resp_alto = cliente.put("/regras/limite", json={"limite_confianca": 1.05})
    assert resp_alto.status_code == 422


def test_put_regras_limite_valido_cria_versao(cliente):
    """PUT /regras/limite com 0.90 valida o valor, grava a configuração e cria nova versão."""
    resp = cliente.put(
        "/regras/limite",
        json={"limite_confianca": 0.90, "auditora": "Dra. Renata Silveira"},
    )
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["limite_confianca"] == 0.90
    assert dados["versao"] == "v2"
    assert dados["atualizado_por"] == "Dra. Renata Silveira"
    assert dados["atualizado_em"] is not None

    # Consulta via GET /regras/limite confirma os dados
    get_resp = cliente.get("/regras/limite")
    assert get_resp.status_code == 200
    get_dados = get_resp.json()
    assert get_dados["limite_confianca"] == 0.90
    assert get_dados["versao"] == "v2"


# ---------------------------------------------------------------------------
# Cenários 1 & 2: Novo documento vai para revisão humana, documento já processado mantém destino
# ---------------------------------------------------------------------------
def test_cenario_alteracao_limite_novo_vai_a_revisao_e_processado_mantem_destino(
    cliente,
):
    """Critérios de aceite H6.1.1:
    - Dado o limite inicial de 0.80, DOC-001 com score 0.85 é processado e segue para Farmacia_Hospitalar.
    - O limite é alterado de 0.80 para 0.90.
    - Quando um novo documento DOC-002 com score 0.85 chega, ele vai para Fila_Revisao_Humana.
    - Então DOC-001 (já processado) não muda de destino ao ser consultado.
    """
    ext_085 = Extracao(
        tipo_documento="Receituário Médico",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.85,
        paciente=Paciente(nome="Carlos Andrade"),
        medico_solicitante=MedicoSolicitante(
            nome="Dr. Lucas Mendes", crm="CRM 12345 SP"
        ),
        medicamentos=[Medicamento(nome="Paracetamol", dose="500mg")],
    )

    texto_completo = (
        "RECEITUARIO. Paciente: Carlos Andrade, 45 anos. "
        "Dr. Lucas Mendes CRM 12345 SP. "
        "Medicamento: Paracetamol 500mg de 8 em 8 horas."
    )

    # 1. Processa DOC-001 com limite padrão (0.80). Score 0.85 >= 0.80 -> destino normal
    corpo_doc1 = {
        "documento_id": "DOC-ANTIGO-001",
        "tipo_arquivo": "TEXTO",
        "documento_texto": texto_completo,
        "canal_origem": "Ambulatorio",
    }
    d_antigo = processar(
        corpo_doc1["documento_id"],
        corpo_doc1["documento_texto"],
        None,
        extrator=extrator_fixo(ext_085),
    )
    r_antigo = ResultadoTriagem.model_validate(d_antigo)
    assert r_antigo.decisao_roteamento.destino_principal == Destino.FARMACIA_HOSPITALAR
    assert r_antigo.decisao_roteamento.requer_auditoria_humana is False
    assert r_antigo.versao_regras == "v1"

    # 2. Altera o limite para 0.90 via API (passa a ser versão v2)
    put_resp = cliente.put(
        "/regras/limite",
        json={"limite_confianca": 0.90, "auditora": "Auditora Chefe"},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["limite_confianca"] == 0.90

    # 3. Novo documento DOC-002 chega com score 0.85 (< 0.90) -> Deve ir para Fila_Revisao_Humana
    corpo_doc2 = {
        "documento_id": "DOC-NOVO-002",
        "tipo_arquivo": "TEXTO",
        "documento_texto": texto_completo,
        "canal_origem": "Ambulatorio",
    }
    d_novo = processar(
        corpo_doc2["documento_id"],
        corpo_doc2["documento_texto"],
        None,
        extrator=extrator_fixo(ext_085),
    )
    r_novo = ResultadoTriagem.model_validate(d_novo)
    assert r_novo.decisao_roteamento.destino_principal == Destino.FILA_REVISAO_HUMANA
    assert r_novo.decisao_roteamento.requer_auditoria_humana is True
    assert r_novo.versao_regras == "v2"

    # 4. Documento DOC-ANTIGO-001 já processado mantém seu destino original
    get_doc1 = cliente.get("/documentos/DOC-ANTIGO-001")
    assert get_doc1.status_code == 200
    doc1_carregado = ResultadoTriagem.model_validate(get_doc1.json())
    assert (
        doc1_carregado.decisao_roteamento.destino_principal
        == Destino.FARMACIA_HOSPITALAR
    )
    assert doc1_carregado.decisao_roteamento.requer_auditoria_humana is False
    assert doc1_carregado.versao_regras == "v1"


# ---------------------------------------------------------------------------
# Validação direta do modelo RegrasConfig
# ---------------------------------------------------------------------------
def test_regras_config_limites_permitidos():
    """RegrasConfig aceita valores no intervalo [0.50, 0.99] e rejeita fora dele."""
    # Valores válidos nos extremos e no meio
    cfg_min = RegrasConfig(limite_confianca=0.50)
    assert cfg_min.limite_confianca == 0.50

    cfg_max = RegrasConfig(limite_confianca=0.99)
    assert cfg_max.limite_confianca == 0.99

    cfg_mid = RegrasConfig(limite_confianca=0.85)
    assert cfg_mid.limite_confianca == 0.85

    # Valores inválidos abaixo de 0.50 ou acima de 0.99
    with pytest.raises(ValidationError):
        RegrasConfig(limite_confianca=0.49)

    with pytest.raises(ValidationError):
        RegrasConfig(limite_confianca=1.00)

    with pytest.raises(ValidationError):
        RegrasConfig(limite_confianca=0.0)


def test_servico_regras_persistencia_e_recuperacao():
    """ServicoRegras salva no storage e recupera as regras dinâmicas."""
    srv = servico_regras()
    nova_cfg = srv.atualizar_limite(0.92, auditora="Dra. Ana")
    assert nova_cfg.limite_confianca == 0.92
    assert nova_cfg.versao == "v2"

    # Leitura subsequente reflete o valor salvo
    lida = srv.obter_regras()
    assert lida.limite_confianca == 0.92
    assert lida.versao == "v2"
    assert lida.atualizado_por == "Dra. Ana"
