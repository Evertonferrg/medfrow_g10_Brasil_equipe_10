"""H4.1.1 T5 — Testes para barrar documentos de baixa confiança.

Cenários conforme critérios de aceite:
  1. Score global 0.79 vai à revisão e 0.80 segue.
  2. Score global 0.95 com dose em 0.50 vai à revisão (campo crítico baixo).
  3. Nenhum documento do conjunto abaixo do limite é roteado (tabela parametrizada).
  4. Configuração de campos críticos em config/regras.json.
  5. Cálculo do score global = min(score_classificacao, media_scores_campos).
"""

import pytest

from app import config
from app.confianca import (
    avaliar_confianca,
    calcular_score_global,
    obter_scores_campos,
)
from app.grafo import triar
from app.modelos import Destino
from app.schemas import (
    Extracao,
    Medicamento,
    MedicoSolicitante,
    Paciente,
)
from testes.conftest import extrator_fixo


# ---------------------------------------------------------------------------
# T1: Configurar os campos críticos
# ---------------------------------------------------------------------------
def test_t1_campos_criticos_configurados_e_acessiveis():
    """T1: Verifica se os campos críticos esperados estão definidos e acessíveis via config."""
    campos = config.campos_criticos()
    esperados = [
        "paciente.nome",
        "medico_solicitante.crm",
        "medicamentos.nome",
        "medicamentos.dose",
        "cid_sugerido",
    ]
    for campo in esperados:
        assert campo in campos, f"Campo crítico '{campo}' ausente da configuração"


# ---------------------------------------------------------------------------
# T2: Definir o score global
# ---------------------------------------------------------------------------
def test_t2_score_global_menor_valor_entre_classificacao_e_media_campos():
    """T2: score global = min(score_classificacao, media_scores_campos)."""
    # Caso 1: classificação menor que a média dos campos
    # campos com média 0.90, classificação 0.75 -> score global 0.75
    scores_campos = {"paciente.nome": 1.0, "medico_solicitante.crm": 0.8}
    assert calcular_score_global(0.75, scores_campos) == 0.75

    # Caso 2: média dos campos menor que a classificação
    # campos com média 0.60, classificação 0.95 -> score global 0.60
    scores_campos = {"paciente.nome": 0.8, "medico_solicitante.crm": 0.4}
    assert calcular_score_global(0.95, scores_campos) == 0.60

    # Caso 3: sem campos de score -> devolve o próprio score de classificação
    assert calcular_score_global(0.85, {}) == 0.85


# ---------------------------------------------------------------------------
# T3 e T5: Avaliar confiança e cenários de aceite
# ---------------------------------------------------------------------------
def test_t3_t5_score_079_vai_a_revisao_e_080_segue():
    """Critério 1: Score 0.79 vai à revisão e 0.80 segue."""
    ext = Extracao(
        tipo_documento="Receituário Médico",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.79,
        paciente=Paciente(nome="Maria Souza"),
        medico_solicitante=MedicoSolicitante(nome="Dr. Paulo Lima", crm="CRM 99887 SP"),
        medicamentos=[Medicamento(nome="Amoxicilina", dose="500mg")],
    )

    # 0.79 < 0.80 -> Deve ir para revisão com motivo explícito
    score_glob, motivos, requer_rev = avaliar_confianca(0.79, ext, limite=0.80)
    assert requer_rev is True
    assert score_glob == 0.79
    assert any("score global abaixo do limite" in m for m in motivos)

    # 0.80 >= 0.80 -> Não deve ir para revisão se campos estiverem confiáveis
    score_glob, motivos, requer_rev = avaliar_confianca(0.80, ext, limite=0.80)
    assert requer_rev is False
    assert len(motivos) == 0


def test_t3_t5_score_global_095_com_dose_050_vai_a_revisao():
    """Critério 2: Score global 0.95 com dose em 0.50 vai à revisão por campo crítico baixo."""
    ext = Extracao(
        tipo_documento="Receituário Médico",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.95,
        paciente=Paciente(nome="Maria Souza"),
        medico_solicitante=MedicoSolicitante(nome="Dr. Paulo Lima", crm="CRM 99887 SP"),
        medicamentos=[Medicamento(nome="Amoxicilina", dose="500mg")],
    )

    scores_customizados = {
        "paciente.nome": 1.0,
        "medico_solicitante.crm": 1.0,
        "medicamentos.nome": 1.0,
        "medicamentos.dose": 0.50,  # campo crítico abaixo de 0.80
    }

    score_glob, motivos, requer_rev = avaliar_confianca(
        0.95, ext, limite=0.80, scores_campos=scores_customizados
    )

    assert requer_rev is True
    # O motivo deve citar explicitamente o campo medicamentos.dose
    assert any("medicamentos.dose" in m for m in motivos)


@pytest.mark.parametrize(
    "tipo_doc,score",
    [
        ("Receituário Médico", 0.79),
        ("Receituário Médico", 0.50),
        ("Guia de Solicitação de Procedimento", 0.75),
        ("Laudo de Exame de Imagem", 0.60),
        ("Relatório de Alta", 0.70),
        ("Atestado Médico", 0.78),
    ],
)
def test_t5_nenhum_documento_do_conjunto_abaixo_do_limite_e_roteado(tipo_doc, score):
    """Critério 3: Qualquer documento com score abaixo do limite é barrado e vai para revisão."""
    ext = Extracao(
        tipo_documento=tipo_doc,
        nivel_prioridade="Rotina",
        score_confianca_classificacao=score,
        paciente=Paciente(nome="Maria Souza"),
        medico_solicitante=MedicoSolicitante(nome="Dr. Paulo Lima", crm="CRM 99887 SP"),
    )

    score_glob, motivos, requer_rev = avaliar_confianca(score, ext, limite=0.80)
    assert requer_rev is True
    assert score_glob < 0.80
    assert any("score global abaixo do limite" in m for m in motivos)


# ---------------------------------------------------------------------------
# T4 e Grafo: nó enviar_revisao e salvamento de estado completo
# ---------------------------------------------------------------------------
def test_t4_documento_com_baixa_confianca_vai_para_revisao_via_grafo():
    """T4: Documento barrado por confiança recebe destino Fila_Revisao_Humana e grava estado."""
    ext = Extracao(
        tipo_documento="Receituário Médico",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.75,  # abaixo de 0.80
        paciente=Paciente(nome="Maria Souza"),
        medico_solicitante=MedicoSolicitante(nome="Dr. Paulo Lima", crm="CRM 99887 SP"),
        medicamentos=[Medicamento(nome="Amoxicilina", dose="500mg")],
    )
    texto = (
        "RECEITUARIO. Paciente: Maria Souza, 40 anos. Dr. Paulo Lima CRM 99887 SP. "
        "Amoxicilina 500mg de 8 em 8 horas por 7 dias."
    )

    estado = triar(texto, extrator_fixo(ext))
    assert estado["destino"] == Destino.FILA_REVISAO_HUMANA.value or estado["destino"] == Destino.FILA_REVISAO_HUMANA
    assert estado["requer_revisao"] is True
    resultado = estado.get("resultado")
    assert resultado is not None
    assert resultado["decisao_roteamento"]["destino_principal"] == "Fila_Revisao_Humana"
    assert resultado["decisao_roteamento"]["requer_auditoria_humana"] is True
