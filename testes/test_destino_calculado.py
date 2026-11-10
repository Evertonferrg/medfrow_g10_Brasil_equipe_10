"""destino_sem_revisao (grafo.py): roda no repositório, com o roteamento simulado."""

from types import SimpleNamespace

import pytest

from app import grafo
from app.modelos import Classificacao, Destino, TipoDocumento


def classificacao(tipo="Receituário Médico", score=0.3, prioridade="Rotina"):
    return Classificacao(
        tipo_documento=tipo,
        especialidade="Ortopedia",
        nivel_prioridade=prioridade,
        score_confianca_classificacao=score,
    )


@pytest.fixture
def roteamento(monkeypatch):
    chamadas = []

    def falso(estado, limite_confianca):
        chamadas.append(estado)
        return SimpleNamespace(destino_principal="Farmacia_Hospitalar")

    monkeypatch.setattr(grafo.rt, "criar_decisao_roteamento", falso)
    return chamadas


def test_ignora_score_baixo_e_problemas_e_devolve_o_destino(roteamento):
    extracao = object()
    destino = grafo.destino_sem_revisao(extracao, classificacao(score=0.3), 0.8)
    assert destino == "Farmacia_Hospitalar"
    visto = roteamento[0]
    assert visto["score"] == 1.0 and visto["problemas"] == []
    assert visto["motivos_revisao"] == [] and visto["requer_revisao"] is False
    assert visto["classificacao"].score_confianca_classificacao == 1.0
    assert visto["extracao"] is extracao


def test_sem_destino_possivel_devolve_none_sem_chamar_o_roteamento(roteamento):
    nao_id = classificacao(tipo=TipoDocumento.NAO_IDENTIFICADO)
    assert grafo.destino_sem_revisao(object(), nao_id, 0.8) is None
    assert grafo.destino_sem_revisao(None, classificacao(), 0.8) is None
    assert grafo.destino_sem_revisao(object(), None, 0.8) is None
    assert roteamento == []


def test_se_o_roteamento_ainda_manda_para_revisao_nao_ha_destino(monkeypatch):
    monkeypatch.setattr(
        grafo.rt,
        "criar_decisao_roteamento",
        lambda estado, limite_confianca: SimpleNamespace(
            destino_principal=Destino.FILA_REVISAO_HUMANA
        ),
    )
    assert grafo.destino_sem_revisao(object(), classificacao(), 0.8) is None


def test_falha_no_roteamento_vira_none(monkeypatch):
    def quebra(estado, limite_confianca):
        raise ValueError("x")

    monkeypatch.setattr(grafo.rt, "criar_decisao_roteamento", quebra)
    assert grafo.destino_sem_revisao(object(), classificacao(), 0.8) is None
