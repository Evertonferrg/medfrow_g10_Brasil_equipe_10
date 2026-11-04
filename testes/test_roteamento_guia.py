"""H2.1.2 — Enviar guias à Auditoria de Autorizações.

Cenários cobertos:
1. Tabela parametrizada: precedência estrita (urgência → revisão → tipo) para guias;
2. Determinismo: a mesma entrada de guia executada 10 vezes devolve exatamente o mesmo destino;
3. Critérios de aceite ponta a ponta:
   - Guia de rotina com confiança acima do limite vai para Auditoria_Autorizacoes;
   - Os exames ou procedimentos (exames/exames_solicitados), médico solicitante e CID seguem preenchidos;
4. Guia Urgente não vai para Auditoria_Autorizacoes (vai para Fila_Emergencia_Medica com alerta);
5. Guia com score baixo (< limite) vai para Fila_Revisao_Humana;
6. Guia com pendência/problemas vai para Fila_Revisao_Humana;
7. Integração via API FastAPI (/triagem e /documentos/{id}) entrega destino e dados completos.
"""

import pytest

from app import config
from app.grafo import triar
from app.modelos import Destino, TipoDocumento
from app.resposta import montar_resposta
from app.roteamento import decidir_destino
from app.schemas import Exame, Extracao, Medico, Paciente
from testes.conftest import cliente_com, extrator_fixo
from testes.fixtures import guias as G


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
        # --- Guias de rotina com score alto e sem pendências -> Auditoria_Autorizacoes
        (
            TipoDocumento.GUIA_PROCEDIMENTO.value,
            0.95,
            False,
            False,
            Destino.AUDITORIA_AUTORIZACOES,
        ),
        (
            "Guia de Solicitação de Procedimento",
            0.80,
            False,
            False,
            Destino.AUDITORIA_AUTORIZACOES,
        ),
        (
            "Guia de Solicitação de Procedimento",
            0.85,
            False,
            [],
            Destino.AUDITORIA_AUTORIZACOES,
        ),
        (
            "Guia",
            0.90,
            False,
            False,
            Destino.AUDITORIA_AUTORIZACOES,
        ),
        # --- Urgência tem precedência sobre a rota de rotina (não vai para auditoria)
        (
            TipoDocumento.GUIA_PROCEDIMENTO.value,
            0.95,
            True,
            False,
            Destino.FILA_EMERGENCIA_MEDICA,
        ),
        (
            "Guia de Solicitação de Procedimento",
            0.85,
            True,
            False,
            Destino.FILA_EMERGENCIA_MEDICA,
        ),
        (
            "Guia de Solicitação de Procedimento",
            0.60,
            True,
            True,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Guia de Solicitação de Procedimento",
            0.50,
            True,
            ["Exame sem código TUSS no texto"],
            Destino.FILA_REVISAO_HUMANA,
        ),
        # --- Revisão tem precedência sobre o tipo de documento
        # Score abaixo do limite (limite = 0.80) -> Fila_Revisao_Humana
        (
            TipoDocumento.GUIA_PROCEDIMENTO.value,
            0.79,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Guia de Solicitação de Procedimento",
            0.50,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        (
            "Guia de Solicitação de Procedimento",
            0.30,
            False,
            False,
            Destino.FILA_REVISAO_HUMANA,
        ),
        # Pendência booleana -> Fila_Revisao_Humana
        (
            "Guia de Solicitação de Procedimento",
            0.95,
            False,
            True,
            Destino.FILA_REVISAO_HUMANA,
        ),
        # Pendência com lista de problemas -> Fila_Revisao_Humana
        (
            "Guia de Solicitação de Procedimento",
            0.95,
            False,
            ["Exame inventado não encontrado no documento"],
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
        # Outro tipo de rotina (Receituário -> Farmácia)
        (
            "Receituário Médico",
            0.95,
            False,
            False,
            Destino.FARMACIA_HOSPITALAR,
        ),
    ],
)
def test_tabela_parametrizada_decidir_destino_guia(
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
def test_determinismo_mesma_guia_executada_10_vezes():
    estado = {
        "tipo_documento": "Guia de Solicitação de Procedimento",
        "score": 0.95,
        "urgencia": False,
        "pendencia": False,
        "problemas": [],
    }
    destinos = [decidir_destino(estado) for _ in range(10)]

    assert len(destinos) == 10
    assert all(d == Destino.AUDITORIA_AUTORIZACOES for d in destinos)
    assert len(set(destinos)) == 1


# ==============================================================================
# 3. Critérios de Aceite Ponta a Ponta:
# Guia acima do limite sem urgência → Auditoria_Autorizacoes com exames, médico e CID
# ==============================================================================
def _criar_extracao_guia(
    urgente: bool = False,
    score: float = 0.95,
    exames: list | None = None,
    medico: Medico | None = None,
    cid: str | None = "M54.5",
) -> Extracao:
    if exames is None:
        exames = [
            Exame(
                nome="Ressonancia magnetica de joelho",
                codigo_tuss="40801020",
            ),
            Exame(
                nome="Ultrassonografia de abdome total",
                codigo_tuss="40901017",
            ),
        ]
    if medico is None:
        medico = Medico(nome="Dra. Ana Torres", crm="CRM-RJ 100002")

    return Extracao(
        tipo_documento=TipoDocumento.GUIA_PROCEDIMENTO,
        especialidade="Ortopedia / Reumatologia",
        nivel_prioridade="Urgente" if urgente else "Rotina",
        score_confianca_classificacao=score,
        paciente=Paciente(nome="Joao Pereira", idade=61),
        medico_solicitante=medico,
        diagnostico_principal="Lumbago com ciatica",
        cid_sugerido=cid,
        cid=cid,
        origem_cid="escrito",
        exames=exames,
        exames_solicitados=exames,
    )


def test_guia_de_rotina_com_confianca_acima_do_limite_vai_para_auditoria_autorizacoes():
    """Critério 1: Dado uma guia de rotina com confiança acima do limite, quando processada,
    então o destino é 'Auditoria_Autorizacoes'.
    Critério 2: Então os exames ou procedimentos e o médico solicitante seguem preenchidos.
    T2: exames_solicitados, medico_solicitante e CID presentes no resultado.
    """
    ext = _criar_extracao_guia(urgente=False, score=0.95)
    texto = G.GUIA_COM_TUSS

    # 1) Execução pelo grafo LangGraph
    estado = triar(texto, extrator_fixo(ext))

    assert estado["destino"] == Destino.AUDITORIA_AUTORIZACOES
    assert estado["requer_revisao"] is False
    assert estado["regra"] == "R-GUIA"
    assert "Auditoria_Autorizacoes" in estado["justificativa"]
    assert "R-GUIA" in estado["justificativa"]

    # 2) Montagem da resposta estruturada
    resultado = montar_resposta("DOC-GUIA-001", estado)

    assert resultado.status == "processado"
    assert (
        resultado.decisao_roteamento.destino_principal == Destino.AUDITORIA_AUTORIZACOES
    )
    assert resultado.decisao_roteamento.requer_auditoria_humana is False
    assert resultado.decisao_roteamento.regra_aplicada == "R-GUIA"
    assert (
        "Auditoria_Autorizacoes"
        in resultado.decisao_roteamento.justificativa_roteamento
    )

    # 3) Conferência dos dados clínicos que seguem com a guia (T2)
    assert resultado.dados_extraidos is not None
    dados = resultado.dados_extraidos

    # Exames e procedimentos (exames e exames_solicitados)
    assert "exames" in dados
    assert "exames_solicitados" in dados
    procs = dados["exames_solicitados"]
    assert len(procs) == 2
    assert procs[0]["nome"] == "Ressonancia magnetica de joelho"
    assert procs[0]["codigo_tuss"] == "40801020"
    assert procs[1]["nome"] == "Ultrassonografia de abdome total"
    assert procs[1]["codigo_tuss"] == "40901017"

    # Médico solicitante
    assert "medico_solicitante" in dados
    assert dados["medico_solicitante"]["nome"] == "Dra. Ana Torres"
    assert dados["medico_solicitante"]["crm"] == "100002-RJ"

    # CID (cid e cid_sugerido)
    assert dados.get("cid_sugerido") == "M54.5"
    assert dados.get("cid") == "M54.5"


# ==============================================================================
# 4. Guia Urgente NÃO vai para Auditoria_Autorizacoes
# Precedência: urgência tem prioridade máxima
# ==============================================================================
def test_guia_com_urgencia_nao_vai_para_auditoria_autorizacoes():
    """Cenário: guia Urgente não vai para Auditoria_Autorizacoes (vai para emergência)."""
    ext = _criar_extracao_guia(urgente=True, score=0.95)
    texto = G.GUIA_COM_TUSS

    estado = triar(texto, extrator_fixo(ext))

    assert estado["destino"] == Destino.FILA_EMERGENCIA_MEDICA
    assert estado["destino"] != Destino.AUDITORIA_AUTORIZACOES
    assert estado["regra"] == "R-URGENCIA"
    assert estado["notificacao"] is not None
    assert estado["notificacao"]["canal"] == "Alerta_Plantao_Medico"

    resultado = montar_resposta("DOC-GUIA-URG-001", estado)
    assert (
        resultado.decisao_roteamento.destino_principal == Destino.FILA_EMERGENCIA_MEDICA
    )
    assert resultado.decisao_roteamento.regra_aplicada == "R-URGENCIA"


# ==============================================================================
# 5. Guia com score baixo vai para revisão humana
# Precedência: segurança / confiabilidade
# ==============================================================================
def test_guia_com_score_baixo_vai_para_revisao():
    """Cenário: guia com score baixo (< 0.80) vai para revisão humana."""
    ext = _criar_extracao_guia(urgente=False, score=0.65)
    texto = G.GUIA_COM_TUSS

    estado = triar(texto, extrator_fixo(ext))

    assert estado["destino"] == Destino.FILA_REVISAO_HUMANA
    assert estado["destino"] != Destino.AUDITORIA_AUTORIZACOES
    assert estado["requer_revisao"] is True
    assert estado["regra"] == "R-REVISAO"

    resultado = montar_resposta("DOC-GUIA-BAIXO-001", estado)
    assert resultado.decisao_roteamento.destino_principal == Destino.FILA_REVISAO_HUMANA
    assert resultado.decisao_roteamento.requer_auditoria_humana is True
    assert resultado.decisao_roteamento.regra_aplicada == "R-REVISAO"


# ==============================================================================
# 6. Guia com pendência de validação vai para revisão humana
# ==============================================================================
def test_guia_com_pendencia_ou_erro_vai_para_revisao():
    """Guia com problema de validação ou pendência não segue para auditoria."""
    ext = _criar_extracao_guia(urgente=False, score=0.95)
    texto = "Guia ilegível sem procedimentos claros."

    # Se a validação apontar problemas, segue para revisão
    estado = triar(
        texto,
        extrator_fixo(ext),
        # simula problema detectado
    )
    # Como o texto não contém os exames da extração, o validador vai descartá-los
    # e registrar problema de exame não encontrado no texto
    assert estado["destino"] == Destino.FILA_REVISAO_HUMANA
    assert estado["requer_revisao"] is True
    assert estado["regra"] == "R-REVISAO"


# ==============================================================================
# 7. Teste de Ponta a Ponta via API HTTP
# ==============================================================================
def test_guia_roteada_via_api_entrega_destino_e_dados_completos():
    ext = _criar_extracao_guia(urgente=False, score=0.95)
    cliente = cliente_com(extrator_fixo(ext))

    payload = {
        "documento_id": "GUIA-AUDIT-2026-001",
        "tipo_arquivo": "TEXTO",
        "documento_texto": G.GUIA_COM_TUSS,
        "canal_origem": "Operadora",
    }

    resp = cliente.post("/triagem?aguardar=true", json=payload)
    assert resp.status_code == 200

    dados = resp.json()
    # 1) Roteamento para Auditoria_Autorizacoes
    decisao = dados["decisao_roteamento"]
    assert decisao["destino_principal"] == "Auditoria_Autorizacoes"
    assert decisao["requer_auditoria_humana"] is False
    assert decisao["regra_aplicada"] == "R-GUIA"
    assert "Auditoria_Autorizacoes" in decisao["justificativa_roteamento"]

    # 2) Dados clínicos que seguem com a guia
    extraidos = dados["dados_extraidos"]
    assert extraidos is not None

    # Exames e procedimentos com TUSS
    assert "exames" in extraidos
    assert "exames_solicitados" in extraidos
    assert len(extraidos["exames_solicitados"]) == 2
    assert extraidos["exames_solicitados"][0]["codigo_tuss"] == "40801020"
    assert extraidos["exames_solicitados"][1]["codigo_tuss"] == "40901017"

    # Médico solicitante
    assert extraidos["medico_solicitante"]["nome"] == "Dra. Ana Torres"
    assert extraidos["medico_solicitante"]["crm"] == "100002-RJ"

    # CID
    assert extraidos.get("cid_sugerido") == "M54.5"
    assert extraidos.get("cid") == "M54.5"

    # 3) Persistência consultável via GET /documentos/{id}
    resp_get = cliente.get("/documentos/GUIA-AUDIT-2026-001")
    assert resp_get.status_code == 200
    dados_get = resp_get.json()
    assert (
        dados_get["decisao_roteamento"]["destino_principal"] == "Auditoria_Autorizacoes"
    )
    assert len(dados_get["dados_extraidos"]["exames_solicitados"]) == 2
