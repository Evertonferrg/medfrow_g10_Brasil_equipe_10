"""H2.1.3 — Enviar laudos, altas e atestados ao Prontuário.

Cenários cobertos:
1. Tabela parametrizada: precedência estrita (urgência → revisão → tipo) para
   laudos de exame, relatórios de alta e atestados médicos;
2. Determinismo: a mesma entrada executada 10 vezes devolve sempre o mesmo destino;
3. Critérios de aceite ponta a ponta:
   - Laudo sem achado crítico (Rotina) segue para "Prontuario_Eletronico";
   - Relatório de alta de rotina segue para "Prontuario_Eletronico";
   - Atestado médico de rotina segue para "Prontuario_Eletronico";
4. Precedência da urgência (T2): laudo com prioridade "Urgente" segue para a emergência,
   NUNCA para o Prontuário;
5. Segurança: documentos com score baixo (< limite) ou pendências seguem para revisão humana;
6. Integração via API FastAPI (/triagem e /documentos/{id}) com persistência em processados/rotina.
"""

import pytest

from app import config
from app.grafo import triar
from app.modelos import Destino, TipoDocumento
from app.resposta import montar_resposta
from app.roteamento import decidir_destino
from app.schemas import Extracao, Medico, Paciente
from testes.conftest import cliente_com, extrator_fixo


@pytest.fixture(autouse=True)
def limite_de_teste(monkeypatch):
    monkeypatch.setattr(config, "limite_confianca", lambda: 0.80)
    monkeypatch.setattr(config, "limiar_confianca", lambda: 0.80)


# ==============================================================================
# 1. Tabela Parametrizada (tipo, score, urgência, pendência → destino)
# Precedência estrita: urgência → revisão → tipo (T1 e T2)
# ==============================================================================
@pytest.mark.parametrize(
    "tipo, score, urgencia, pendencia, destino_esperado",
    [
        # --- T1: Laudos sem achado crítico (Rotina) -> Prontuario_Eletronico
        (
            TipoDocumento.LAUDO_IMAGEM.value,
            0.95,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Laudo de Exame de Imagem",
            0.80,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            TipoDocumento.LAUDO_LABORATORIAL.value,
            0.92,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Laudo Laboratorial",
            0.85,
            False,
            [],
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Laudo de Exame",
            0.90,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Laudo",
            0.91,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        # --- T1: Relatórios de alta -> Prontuario_Eletronico
        (
            TipoDocumento.RELATORIO_ALTA.value,
            0.88,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Relatório de Alta",
            0.85,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Relatório de Alta/Internação",
            0.93,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Relatório de Internação",
            0.86,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        (
            "Alta",
            0.89,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        # --- T1: Atestados médicos -> Prontuario_Eletronico
        (
            TipoDocumento.ATESTADO_MEDICO.value,
            0.85,
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
        (
            "Atestado",
            0.85,
            False,
            False,
            Destino.PRONTUARIO_ELETRONICO,
        ),
        # --- T2: Precedência da Urgência: casos críticos NÃO vão para Prontuário
        (
            TipoDocumento.LAUDO_IMAGEM.value,
            0.95,
            True,
            False,
            Destino.FILA_EMERGENCIA_MEDICA,
        ),
        (
            "Laudo de Exame de Imagem",
            0.90,
            True,
            False,
            Destino.FILA_EMERGENCIA_MEDICA,
        ),
        (
            TipoDocumento.LAUDO_LABORATORIAL.value,
            0.95,
            True,
            False,
            Destino.FILA_EMERGENCIA_MEDICA,
        ),
        (
            "Relatório de Alta",
            0.92,
            True,
            False,
            Destino.FILA_EMERGENCIA_MEDICA,
        ),
        (
            "Atestado Médico",
            0.95,
            True,
            False,
            Destino.FILA_EMERGENCIA_MEDICA,
        ),
        # --- Precedência de Revisão Humana sobre Tipo e Urgência com pendência
        (
            "Laudo de Exame de Imagem",
            0.79,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Relatório de Alta",
            0.50,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Atestado Médico",
            0.60,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Laudo de Exame de Imagem",
            0.95,
            False,
            True,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Relatório de Alta",
            0.95,
            False,
            ["Inconsistência de data"],
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Laudo de Exame de Imagem",
            0.60,
            True,
            True,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Desconhecido",
            0.95,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        # --- Outros tipos de rotina para comparação
        (
            "Receituário Médico",
            0.95,
            False,
            False,
            Destino.FARMACIA_HOSPITALAR,
        ),
        (
            "Guia de Solicitação de Procedimento",
            0.95,
            False,
            False,
            Destino.AUDITORIA_AUTORIZACOES,
        ),
    ],
)
def test_tabela_parametrizada_decidir_destino_prontuario(
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
# 2. Determinismo: mesma entrada executada 10 vezes devolve o mesmo destino
# ==============================================================================
@pytest.mark.parametrize(
    "tipo_doc",
    [
        "Laudo de Exame de Imagem",
        "Laudo Laboratorial",
        "Relatório de Alta",
        "Atestado Médico",
    ],
)
def test_determinismo_documentos_prontuario_executados_10_vezes(tipo_doc):
    estado = {
        "tipo_documento": tipo_doc,
        "score": 0.95,
        "urgencia": False,
        "pendencia": False,
        "problemas": [],
    }
    destinos = [decidir_destino(estado) for _ in range(10)]

    assert len(destinos) == 10
    assert all(d == Destino.PRONTUARIO_ELETRONICO for d in destinos)
    assert len(set(destinos)) == 1


# ==============================================================================
# 3. Critérios de Aceite Ponta a Ponta:
# Laudo sem achado crítico → Prontuario_Eletronico
# Relatório de alta e Atestado → Prontuario_Eletronico
# ==============================================================================
def _criar_extracao(
    tipo: str,
    urgente: bool = False,
    score: float = 0.95,
    especialidade: str = "Clínica Médica",
    achado: str | None = None,
    cid: str | None = None,
) -> Extracao:
    return Extracao(
        tipo_documento=tipo,
        especialidade=especialidade,
        nivel_prioridade="Urgente" if urgente else "Rotina",
        score_confianca_classificacao=score,
        paciente=Paciente(nome="Maria Aparecida da Silva", idade=54),
        medico_solicitante=Medico(nome="Dr. Roberto Neves", crm="112233-SP"),
        diagnostico_principal=achado,
        cid_sugerido=cid,
        cid=cid,
        origem_cid="escrito" if cid else None,
    )


def test_laudo_sem_achado_critico_vai_para_prontuario_eletronico():
    """Critério 1: Dado um laudo sem achado crítico, quando processado,
    então o destino é 'Prontuario_Eletronico'.
    """
    ext = _criar_extracao(
        tipo=TipoDocumento.LAUDO_IMAGEM.value,
        urgente=False,
        score=0.95,
        especialidade="Radiologia",
        achado="Radiografia de tórax dentro dos padrões da normalidade",
    )
    texto = (
        "HOSPITAL CENTRAL - LAUDO RADIOLÓGICO. Paciente: Maria Aparecida da Silva, 54 anos. "
        "Dr. Roberto Neves CRM-SP 112233. Raio-X de Tórax PA e Perfil. "
        "Achados: Campos pleuropulmonares limpos e transparentes. Área cardíaca de dimensões normais. "
        "Conclusão: Exame dentro dos padrões da normalidade."
    )

    # 1) Execução pelo grafo LangGraph
    estado = triar(texto, extrator_fixo(ext))

    assert estado["destino"] == Destino.PRONTUARIO_ELETRONICO
    assert estado["requer_revisao"] is False
    assert estado["regra"] == "R-PRONTUARIO"
    assert "Prontuario_Eletronico" in estado["justificativa"]
    assert "R-PRONTUARIO" in estado["justificativa"]

    # 2) Montagem da resposta estruturada
    resultado = montar_resposta("DOC-LAUDO-001", estado)

    assert resultado.status == "processado"
    assert (
        resultado.decisao_roteamento.destino_principal == Destino.PRONTUARIO_ELETRONICO
    )
    assert resultado.decisao_roteamento.requer_auditoria_humana is False
    assert resultado.decisao_roteamento.regra_aplicada == "R-PRONTUARIO"
    assert (
        "Prontuario_Eletronico" in resultado.decisao_roteamento.justificativa_roteamento
    )


def test_laudo_laboratorial_de_rotina_vai_para_prontuario_eletronico():
    """Laudo laboratorial sem achados críticos vai para Prontuario_Eletronico."""
    ext = _criar_extracao(
        tipo=TipoDocumento.LAUDO_LABORATORIAL.value,
        urgente=False,
        score=0.92,
        especialidade="Patologia Clínica",
        achado="Hemograma com parâmetros fisiológicos normais",
    )
    texto = (
        "LABORATÓRIO CENTRAL. Paciente: Maria Aparecida da Silva, 54 anos. "
        "Dr. Roberto Neves CRM 112233 SP. Hemograma completo: Hemoglobina 14,0 g/dL, "
        "Leucócitos 6.500/mm3, Plaquetas 240.000/mm3. Todos os parâmetros dentro da normalidade."
    )

    estado = triar(texto, extrator_fixo(ext))

    assert estado["destino"] == Destino.PRONTUARIO_ELETRONICO
    assert estado["requer_revisao"] is False
    assert estado["regra"] == "R-PRONTUARIO"


def test_relatorio_de_alta_vai_para_prontuario_eletronico():
    """Critério 2: Dado um relatório de alta, quando processado,
    então o destino também é 'Prontuario_Eletronico'.
    """
    ext = _criar_extracao(
        tipo=TipoDocumento.RELATORIO_ALTA.value,
        urgente=False,
        score=0.90,
        especialidade="Clínica Médica",
        achado="Alta hospitalar após recuperação clínica satisfatória",
        cid="K29.7",
    )
    texto = (
        "RELATÓRIO DE ALTA HOSPITALAR. Paciente: Maria Aparecida da Silva, 54 anos. "
        "Médico Assistente: Dr. Roberto Neves CRM-SP 112233. "
        "Internação: 3 dias por gastrite aguda (CID K29.7). "
        "Evolução favorável, sem queixas. Alta hospitalar em boas condições clínicas, "
        "com orientações e retorno ambulatorial em 15 dias."
    )

    estado = triar(texto, extrator_fixo(ext))

    assert estado["destino"] == Destino.PRONTUARIO_ELETRONICO
    assert estado["requer_revisao"] is False
    assert estado["regra"] == "R-PRONTUARIO"

    resultado = montar_resposta("DOC-ALTA-001", estado)
    assert (
        resultado.decisao_roteamento.destino_principal == Destino.PRONTUARIO_ELETRONICO
    )
    assert resultado.decisao_roteamento.requer_auditoria_humana is False
    assert resultado.decisao_roteamento.regra_aplicada == "R-PRONTUARIO"


def test_atestado_medico_vai_para_prontuario_eletronico():
    """Critério 2: Dado um atestado médico, quando processado,
    então o destino também é 'Prontuario_Eletronico'.
    """
    ext = _criar_extracao(
        tipo=TipoDocumento.ATESTADO_MEDICO.value,
        urgente=False,
        score=0.93,
        especialidade="Medicina do Trabalho / Clínica",
        achado="Repouso por 3 dias devido a quadro infeccioso leve",
        cid="J00",
    )
    texto = (
        "ATESTADO MÉDICO. Atesto para os devidos fins que a paciente Maria Aparecida da Silva, "
        "54 anos, esteve sob meus cuidados médicos no dia de hoje e necessita de 3 (três) dias "
        "de repouso por motivo de saúde (CID-10 J00). "
        "São Paulo, Dr. Roberto Neves CRM 112233 SP."
    )

    estado = triar(texto, extrator_fixo(ext))

    assert estado["destino"] == Destino.PRONTUARIO_ELETRONICO
    assert estado["requer_revisao"] is False
    assert estado["regra"] == "R-PRONTUARIO"

    resultado = montar_resposta("DOC-ATEST-001", estado)
    assert (
        resultado.decisao_roteamento.destino_principal == Destino.PRONTUARIO_ELETRONICO
    )
    assert resultado.decisao_roteamento.requer_auditoria_humana is False
    assert resultado.decisao_roteamento.regra_aplicada == "R-PRONTUARIO"


# ==============================================================================
# 4. T2 — Garantir a precedência da urgência:
# Laudo com nivel_prioridade = "Urgente" segue para emergência, NÃO Prontuário
# ==============================================================================
def test_laudo_com_prioridade_urgente_injetada_segue_para_emergencia():
    """T2: laudo com nivel_prioridade = 'Urgente' segue para a emergência.
    O teste injeta a prioridade direto no estado ou extração.
    """
    ext = _criar_extracao(
        tipo=TipoDocumento.LAUDO_IMAGEM.value,
        urgente=True,
        score=0.95,
        especialidade="Radiologia / Pneumologia",
        achado="Tromboembolismo Pulmonar Agudo",
        cid="I26.9",
    )
    texto = (
        "HOSPITAL SANTA LÚCIA - LAUDO DE TOMOGRAFIA DE TÓRAX. "
        "Paciente: Maria Aparecida da Silva, 54 anos. Dr. Roberto Neves CRM-SP 112233. "
        "Achados: Falha de enchimento em artéria pulmonar principal direita compatível com TEP agudo. "
        "Conclusão: Tromboembolismo pulmonar agudo. Sugere-se conduta clínica urgente."
    )

    estado = triar(texto, extrator_fixo(ext))

    # Precedência: emergência médica, NÃO prontuário
    assert estado["destino"] == Destino.FILA_EMERGENCIA_MEDICA
    assert estado["destino"] != Destino.PRONTUARIO_ELETRONICO
    assert estado["regra"] == "R-URGENCIA"
    assert estado["notificacao"] is not None
    assert estado["notificacao"]["canal"] == "Alerta_Plantao_Medico"

    resultado = montar_resposta("DOC-TEP-001", estado)
    assert (
        resultado.decisao_roteamento.destino_principal == Destino.FILA_EMERGENCIA_MEDICA
    )
    assert resultado.decisao_roteamento.regra_aplicada == "R-URGENCIA"
    assert resultado.decisao_roteamento.requer_auditoria_humana is False


def test_injecao_direta_de_nivel_prioridade_urgente_no_estado_decidir_destino():
    """T2: até H3.1.1 existir, o teste injeta a prioridade direto no estado."""
    estado = {
        "tipo_documento": "Laudo de Exame de Imagem",
        "nivel_prioridade": "Urgente",
        "score": 0.95,
        "problemas": [],
    }
    destino = decidir_destino(estado)
    assert destino == Destino.FILA_EMERGENCIA_MEDICA
    assert destino != Destino.PRONTUARIO_ELETRONICO


# ==============================================================================
# 5. Score baixo e falhas vão para revisão humana (segurança)
# ==============================================================================
@pytest.mark.parametrize(
    "tipo_doc",
    [
        "Laudo de Exame de Imagem",
        "Relatório de Alta",
        "Atestado Médico",
    ],
)
def test_documentos_prontuario_com_score_baixo_vao_para_revisao(tipo_doc):
    ext = _criar_extracao(tipo=tipo_doc, urgente=False, score=0.60)
    texto = f"Documento do tipo {tipo_doc} com baixa qualidade de leitura."

    estado = triar(texto, extrator_fixo(ext))

    assert estado["destino"] == Destino.FILA_REVISAO_HUMANA
    assert estado["destino"] != Destino.PRONTUARIO_ELETRONICO
    assert estado["requer_revisao"] is True
    assert estado["regra"] == "R-REVISAO"


# ==============================================================================
# 6. Teste de Ponta a Ponta via API HTTP
# ==============================================================================
def test_laudo_rotina_via_api_vai_para_prontuario_e_armazena_em_rotina():
    ext = _criar_extracao(
        tipo=TipoDocumento.LAUDO_IMAGEM.value,
        urgente=False,
        score=0.95,
        especialidade="Radiologia",
        achado="Radiografia sem alterações",
    )
    cliente = cliente_com(extrator_fixo(ext))

    payload = {
        "documento_id": "LAUDO-ROTINA-2026-001",
        "tipo_arquivo": "TEXTO",
        "documento_texto": "Laudo de Radiografia de Tórax normal. Paciente: Maria Aparecida da Silva, 54 anos. Dr. Roberto Neves CRM 112233 SP.",
        "canal_origem": "Ambulatorio",
    }

    resp = cliente.post("/triagem?aguardar=true", json=payload)
    assert resp.status_code == 200

    dados = resp.json()
    assert dados["decisao_roteamento"]["destino_principal"] == "Prontuario_Eletronico"
    assert dados["decisao_roteamento"]["requer_auditoria_humana"] is False
    assert dados["decisao_roteamento"]["regra_aplicada"] == "R-PRONTUARIO"
    assert dados["armazenamento_oci"]["caminho_objeto"].startswith(
        "processados/rotina/"
    )
    assert dados["armazenamento_oci"]["urgente"] is False

    # Persistência via GET /documentos/{id}
    resp_get = cliente.get("/documentos/LAUDO-ROTINA-2026-001")
    assert resp_get.status_code == 200
    assert (
        resp_get.json()["decisao_roteamento"]["destino_principal"]
        == "Prontuario_Eletronico"
    )


def test_relatorio_alta_via_api_vai_para_prontuario():
    ext = _criar_extracao(tipo="Relatório de Alta", urgente=False, score=0.91)
    cliente = cliente_com(extrator_fixo(ext))

    payload = {
        "documento_id": "ALTA-2026-001",
        "tipo_arquivo": "TEXTO",
        "documento_texto": "Relatório de alta médica. Paciente: Maria Aparecida da Silva, 54 anos. Dr. Roberto Neves CRM 112233 SP.",
        "canal_origem": "Ambulatorio",
    }

    resp = cliente.post("/triagem?aguardar=true", json=payload)
    assert resp.status_code == 200
    assert (
        resp.json()["decisao_roteamento"]["destino_principal"]
        == "Prontuario_Eletronico"
    )


def test_atestado_via_api_vai_para_prontuario():
    ext = _criar_extracao(tipo="Atestado Médico", urgente=False, score=0.92)
    cliente = cliente_com(extrator_fixo(ext))

    payload = {
        "documento_id": "ATEST-2026-001",
        "tipo_arquivo": "TEXTO",
        "documento_texto": "Atesto repouso de 2 dias. Paciente: Maria Aparecida da Silva, 54 anos. Dr. Roberto Neves CRM 112233 SP.",
        "canal_origem": "Ambulatorio",
    }

    resp = cliente.post("/triagem?aguardar=true", json=payload)
    assert resp.status_code == 200
    assert (
        resp.json()["decisao_roteamento"]["destino_principal"]
        == "Prontuario_Eletronico"
    )


def test_laudo_urgente_via_api_vai_para_emergencia_nao_prontuario():
    ext = _criar_extracao(tipo="Laudo de Exame de Imagem", urgente=True, score=0.95)
    cliente = cliente_com(extrator_fixo(ext))

    payload = {
        "documento_id": "LAUDO-URG-2026-001",
        "tipo_arquivo": "TEXTO",
        "documento_texto": "Laudo de Tomografia com TEP urgente. Paciente: Maria Aparecida da Silva, 54 anos. Dr. Roberto Neves CRM 112233 SP.",
        "canal_origem": "Pronto_Socorro",
    }

    resp = cliente.post("/triagem?aguardar=true", json=payload)
    assert resp.status_code == 200
    assert (
        resp.json()["decisao_roteamento"]["destino_principal"]
        == "Fila_Emergencia_Medica"
    )
    assert resp.json()["decisao_roteamento"]["regra_aplicada"] == "R-URGENCIA"
    assert resp.json()["armazenamento_oci"]["urgente"] is True
    assert resp.json()["armazenamento_oci"]["caminho_objeto"].startswith(
        "processados/urgentes/"
    )
