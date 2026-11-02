"""H2.1.1 T6 — Testes de envio de receitas à Farmácia Hospitalar.

Cenários cobertos:
1. Tabela parametrizada (tipo, score, urgência, pendência → destino);
2. Determinismo: a mesma entrada executada 10 vezes devolve exatamente o mesmo destino;
3. Critério de aceite ponta a ponta: receita roteada sem urgência e com score >= limite
   vai para Farmacia_Hospitalar e preserva a lista estruturada de medicamentos (H1.3.4).
"""

import pytest

from app import config
from app.grafo import construir_grafo, triar
from app.modelos import Destino, TipoDocumento
from app.resposta import montar_resposta
from app.roteamento import decidir_destino
from app.schemas import Extracao, Medicamento, Medico, Paciente
from testes.conftest import cliente_com, extrator_fixo


@pytest.fixture(autouse=True)
def limite_de_teste(monkeypatch):
    monkeypatch.setattr(config, "limite_confianca", lambda: 0.80)
    monkeypatch.setattr(config, "limiar_confianca", lambda: 0.80)


# ==============================================================================
# 1. Tabela Parametrizada (tipo, score, urgência, pendência → destino)
# Precedência estrita: urgência → revisão → tipo
# ==============================================================================
@pytest.mark.parametrize(
    "tipo, score, urgencia, pendencia, destino_esperado",
    [
        # --- Receitas sem urgência, score alto e sem pendências -> Farmacia_Hospitalar
        (
            TipoDocumento.RECEITUARIO_MEDICO.value,
            0.95,
            False,
            False,
            Destino.FARMACIA_HOSPITALAR,
        ),
        (
            "Receituário Médico",
            0.80,
            False,
            False,
            Destino.FARMACIA_HOSPITALAR,
        ),
        (
            "Receituário Médico",
            0.85,
            False,
            [],
            Destino.FARMACIA_HOSPITALAR,
        ),
        # --- Urgência tem precedência máxima (vai para Fila_Emergencia_Medica mesmo sendo receita)
        (
            "Receituário Médico",
            0.95,
            True,
            False,
            Destino.FILA_EMERGENCIA_MEDICA,
        ),
        (
            "Receituário Médico",
            0.60,
            True,
            True,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Receituário Médico",
            0.50,
            True,
            ["Medicamento sem posologia"],
            Destino.FILA_REVISAO_HUMANA,
        ),
        # --- Revisão tem precedência sobre o tipo de documento
        # Score abaixo do limite (limite = 0.80) -> Fila_Revisao_Humana
        (
            "Receituário Médico",
            0.79,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Receituário Médico",
            0.40,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        # Pendência booleana -> Fila_Revisao_Humana
        (
            "Receituário Médico",
            0.90,
            False,
            True,
            Destino.FILA_REVISAO_HUMANA,
        ),
        # Pendência com lista de problemas -> Fila_Revisao_Humana
        (
            "Receituário Médico",
            0.95,
            False,
            ["Medicamento não encontrado no texto original"],
            Destino.FILA_REVISAO_HUMANA,
        ),
        # Tipo Desconhecido -> Fila_Revisao_Humana
        (
            "Desconhecido",
            0.95,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        # --- Outros tipos de rotina
        (
            "Guia de Solicitação de Procedimento",
            0.90,
            False,
            False,
            Destino.AUDITORIA_AUTORIZACOES,
        ),
        (
            "Laudo de Exame de Imagem",
            0.95,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Relatório de Alta",
            0.88,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Atestado Médico",
            0.82,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
    ],
)
def test_tabela_parametrizada_decidir_destino(
    tipo, score, urgencia, pendencia, destino_esperado
):
    estado = {
        "tipo_documento": tipo,
        "score": score,
        "urgencia": urgencia,
        "pendencia": pendencia,
    }
    destino = decidir_destino(estado)
    assert destino == destino_esperado
    assert str(destino) == destino_esperado.value


# ==============================================================================
# 2. Determinismo: mesma entrada 10 vezes devolve o mesmo destino
# ==============================================================================
def test_determinismo_mesma_entrada_executada_10_vezes():
    estado = {
        "tipo_documento": "Receituário Médico",
        "score": 0.95,
        "urgencia": False,
        "pendencia": False,
        "problemas": [],
    }
    destinos = [decidir_destino(estado) for _ in range(10)]

    assert len(destinos) == 10
    assert all(d == Destino.FARMACIA_HOSPITALAR for d in destinos)
    assert len(set(destinos)) == 1


# ==============================================================================
# 3. Critérios de Aceite Ponta a Ponta:
# Receita acima do limite sem urgência → Farmacia_Hospitalar com medicamentos
# ==============================================================================
def _criar_extracao_receita(
    urgente: bool = False,
    score: float = 0.95,
    medicamentos: list | None = None,
) -> Extracao:
    if medicamentos is None:
        medicamentos = [
            Medicamento(
                nome="Amoxicilina",
                dose="500mg",
                frequencia="8 em 8 horas",
                duracao="7 dias",
            ),
            Medicamento(
                nome="Dipirona",
                dose="1g",
                frequencia="se dor ou febre",
                duracao="3 dias",
            ),
        ]
    return Extracao(
        tipo_documento=TipoDocumento.RECEITUARIO_MEDICO,
        especialidade="Clínica Médica",
        nivel_prioridade="Urgente" if urgente else "Rotina",
        score_confianca_classificacao=score,
        paciente=Paciente(nome="Maria Souza", idade=40),
        medico_solicitante=Medico(nome="Dr. Paulo Lima", crm="CRM-SP 99887"),
        medicamentos=medicamentos,
    )


def test_receita_sem_urgencia_com_score_alto_vai_para_farmacia_hospitalar_com_medicamentos():
    ext = _criar_extracao_receita(urgente=False, score=0.95)
    texto = (
        "RECEITUARIO. Paciente: Maria Souza, 40 anos. Dr. Paulo Lima CRM 99887 SP. "
        "Amoxicilina 500mg de 8 em 8 horas por 7 dias. Dipirona 1g se dor ou febre por 3 dias."
    )

    # 1) Execução pelo grafo LangGraph
    estado = triar(texto, extrator_fixo(ext))

    assert estado["destino"] == Destino.FARMACIA_HOSPITALAR
    assert estado["requer_revisao"] is False
    assert estado["regra"] == "R-RECEITA"

    # 2) Montagem da resposta estruturada
    resultado = montar_resposta("DOC-REC-001", estado)

    assert resultado.status == "processado"
    assert resultado.decisao_roteamento.destino_principal == Destino.FARMACIA_HOSPITALAR
    assert resultado.decisao_roteamento.requer_auditoria_humana is False
    assert (
        "Farmacia_Hospitalar" in resultado.decisao_roteamento.justificativa_roteamento
    )

    # A farmácia recebe os medicamentos já estruturados (H1.3.4)
    assert resultado.dados_extraidos is not None
    meds = resultado.dados_extraidos["medicamentos"]
    assert len(meds) == 2
    assert meds[0]["nome"] == "Amoxicilina"
    assert meds[0]["dose"] == "500mg"
    assert meds[0]["frequencia"] == "8 em 8 horas"
    assert meds[0]["duracao"] == "7 dias"
    assert meds[1]["nome"] == "Dipirona"


def test_receita_roteada_via_api_entrega_destino_e_medicamentos():
    meds = [
        Medicamento(
            nome="Amoxicilina",
            dose="500mg",
            frequencia="8 em 8 horas",
            duracao="7 dias",
        )
    ]
    ext = _criar_extracao_receita(urgente=False, score=0.95, medicamentos=meds)
    cliente = cliente_com(extrator_fixo(ext))

    payload = {
        "documento_id": "REC-FARMACIA-101",
        "tipo_arquivo": "TEXTO",
        "documento_texto": (
            "RECEITUARIO. Paciente: Maria Souza, 40 anos. Dr. Paulo Lima CRM 99887 SP. "
            "Amoxicilina 500mg de 8 em 8 horas por 7 dias."
        ),
        "canal_origem": "Ambulatorio",
    }

    resp = cliente.post("/triagem?aguardar=true", json=payload)
    assert resp.status_code == 200

    dados = resp.json()
    assert dados["decisao_roteamento"]["destino_principal"] == "Farmacia_Hospitalar"
    assert dados["decisao_roteamento"]["requer_auditoria_humana"] is False

    medicamentos = dados["dados_extraidos"]["medicamentos"]
    assert len(medicamentos) > 0
    assert medicamentos[0]["nome"] == "Amoxicilina"
    assert medicamentos[0]["dose"] == "500mg"


def test_receita_com_urgencia_vai_para_emergencia_mesmo_com_medicamentos():
    ext = _criar_extracao_receita(urgente=True, score=0.95)
    texto = (
        "RECEITUARIO DE URGENCIA. Paciente: Maria Souza, 40 anos. Dr. Paulo Lima CRM 99887 SP. "
        "Amoxicilina 500mg de 8 em 8 horas por 7 dias. Dipirona 1g se dor ou febre por 3 dias."
    )

    estado = triar(texto, extrator_fixo(ext))
    assert estado["destino"] == Destino.FILA_EMERGENCIA_MEDICA
    assert estado["regra"] == "R-URGENCIA"


def test_receita_com_score_baixo_vai_para_revisao():
    ext = _criar_extracao_receita(urgente=False, score=0.50)
    texto = (
        "RECEITUARIO. Paciente: Maria Souza, 40 anos. Dr. Paulo Lima CRM 99887 SP. "
        "Amoxicilina 500mg de 8 em 8 horas por 7 dias."
    )

    estado = triar(texto, extrator_fixo(ext))
    assert estado["destino"] == Destino.FILA_REVISAO_HUMANA
    assert estado["requer_revisao"] is True
