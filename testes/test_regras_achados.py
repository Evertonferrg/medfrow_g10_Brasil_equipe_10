"""Testes para H6.2.1 — Incluir ou remover achados críticos.

Critérios de aceite:
1. Dado que incluí "pneumotórax hipertensivo", quando chega um laudo com esse achado,
   então ele é marcado Urgente.
2. Dado uma lista vazia, quando tento salvar, então o sistema impede e explica o motivo
   (HTTP 422 com "A lista de achados críticos não pode ficar vazia").
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import regras
from app.api.main import app
from app.grafo import triar
from app.regras import DESTINOS_OFICIAIS, AchadoCritico, RegrasConfig
from app.schemas import Extracao
from app.urgencia import NivelPrioridade, avaliar_urgencia


@pytest.fixture
def cliente():
    return TestClient(app)


@pytest.fixture(autouse=True)
def servico_limpo(monkeypatch, tmp_path):
    """Garante isolamento dos testes de regras usando pasta temporária."""
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
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


# ---------- T1: Validação no Modelo ----------


def test_achado_critico_valida_nome_e_sinonimos():
    # Nome vazio deve falhar
    with pytest.raises(ValidationError):
        AchadoCritico(nome="")

    with pytest.raises(ValidationError):
        AchadoCritico(nome="   ")

    # Nome válido inclui a si mesmo nos sinônimos se não estiver presente
    achado = AchadoCritico(nome="pneumotórax hipertensivo")
    assert achado.nome == "pneumotórax hipertensivo"
    assert "pneumotórax hipertensivo" in achado.sinonimos

    # Aceita lista de sinônimos
    achado2 = AchadoCritico(
        nome="Pneumotórax",
        sinonimos=["pneumotorax hipertensivo", "colapso pulmonar"],
    )
    assert "Pneumotórax" in achado2.sinonimos
    assert "pneumotorax hipertensivo" in achado2.sinonimos


def test_regras_config_recusa_lista_achados_vazia():
    # Lista vazia não deve ser aceita
    with pytest.raises(ValidationError) as exc_info:
        RegrasConfig(achados_criticos=[])
    assert "A lista de achados críticos não pode ficar vazia" in str(exc_info.value)


def test_servico_recusa_atualizar_achados_vazios(servico_limpo):
    with pytest.raises(
        ValueError, match="A lista de achados críticos não pode ficar vazia"
    ):
        servico_limpo.atualizar_achados([])


# ---------- T2: Rota PUT /regras/achados ----------


def test_put_achados_lista_vazia_retorna_422(cliente):
    # Envio de lista vazia no corpo
    resp = cliente.put("/regras/achados", json=[])
    assert resp.status_code == 422
    assert (
        resp.json().get("detail") == "A lista de achados críticos não pode ficar vazia"
    )

    # Envio de dict com lista vazia
    resp2 = cliente.put("/regras/achados", json={"achados_criticos": []})
    assert resp2.status_code == 422
    assert (
        resp2.json().get("detail") == "A lista de achados críticos não pode ficar vazia"
    )


def test_put_achados_e_get_achados(cliente):
    novos = [
        {"nome": "TEP", "sinonimos": ["tromboembolismo pulmonar"]},
        {
            "nome": "pneumotórax hipertensivo",
            "sinonimos": ["pneumotórax hipertensivo", "pneumotórax sob tensão"],
        },
    ]
    resp = cliente.put(
        "/regras/achados", json={"achados_criticos": novos, "auditora": "Dra. Ana"}
    )
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["versao"] == "v2"
    assert dados["atualizado_por"] == "Dra. Ana"

    # Consulta GET
    resp_get = cliente.get("/regras/achados")
    assert resp_get.status_code == 200
    dados_get = resp_get.json()
    nomes = [item["nome"] for item in dados_get["achados_criticos"]]
    assert "pneumotórax hipertensivo" in nomes
    assert "TEP" in nomes


# ---------- T4 e T5: Critério de Aceite 1 ----------


def test_laudo_com_novo_achado_incluido_vira_urgente(servico_limpo, monkeypatch):
    """Dado que incluí 'pneumotórax hipertensivo', quando chega um laudo com esse achado,

    então ele é marcado Urgente.
    """
    # 1. Antes de incluir, pneumotórax hipertensivo não é crítico por padrão
    laudo_texto = (
        "Paciente: Carlos Eduardo Mendes. Solicitante: Dra. Renata Silveira CRM-SP 145892. "
        "RX de tórax evidencia pneumotórax hipertensivo à direita com desvio de mediastino."
    )
    aval_inicial = avaliar_urgencia(laudo_texto, canal="Ambulatorio")
    assert aval_inicial.nivel != NivelPrioridade.URGENTE

    # 2. Auditora inclui "pneumotórax hipertensivo"
    atuais = servico_limpo.obter_regras().achados_criticos
    atuais_lista = [a.model_dump() for a in atuais]
    atuais_lista.append(
        {
            "nome": "pneumotórax hipertensivo",
            "sinonimos": ["pneumotórax hipertensivo", "pneumotorax hipertensivo"],
        }
    )
    servico_limpo.atualizar_achados(atuais_lista, auditora="Dra. Roberta")

    # 3. Agora avaliar_urgencia busca dinamicamente do ServicoRegras
    aval_atualizada = avaliar_urgencia(laudo_texto, canal="Ambulatorio")
    assert aval_atualizada.nivel == NivelPrioridade.URGENTE
    assert "pneumotórax hipertensivo" in aval_atualizada.sinal

    # 4. No fluxo completo do grafo (triar)
    def extrator_falso(txt):
        return Extracao(
            tipo_documento="Laudo de Exame de Imagem",
            especialidade="Radiologia",
            nivel_prioridade="Rotina",
            score_confianca_classificacao=0.95,
            paciente={"nome": "Carlos Eduardo Mendes"},
            medico_solicitante={"nome": "Dra. Renata Silveira", "crm": "CRM-SP 145892"},
        )

    res = triar(laudo_texto, extrator=extrator_falso, canal_origem="Ambulatorio")
    assert res["nivel_prioridade"] == "Urgente"
    assert res["classificacao"].nivel_prioridade == "Urgente"
    assert res["destino"] == "Fila_Emergencia_Medica"
    assert res["regra"] == "R-URGENCIA"
    assert "pneumotórax hipertensivo" in res["justificativa"]
    assert res["notificacao"] is not None
    assert res["notificacao"]["canal"] == "Alerta_Plantao_Medico"
