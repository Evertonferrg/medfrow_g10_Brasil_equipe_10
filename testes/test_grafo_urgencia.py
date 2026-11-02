"""H3.1.1 / H3.1.2 / H3.1.3 ponta a ponta no grafo (extrator e LLM falsos)."""
from types import SimpleNamespace as NS

import pytest
from pydantic import BaseModel, Field

from app.grafo import triar
from app.schemas import MedicoSolicitante
from app.urgencia import fazer_confirmador

NIVEIS = {"Urgente", "Prioritário", "Rotina"}


class Paciente(BaseModel):
    nome: str = "Maria"


class Ext(BaseModel):
    tipo_documento: str = "Receituário Médico"
    especialidade: str = "Clínica Geral"
    nivel_prioridade: str = "Rotina"
    score_confianca_classificacao: float = 0.95
    diagnostico_principal: str | None = None
    paciente: Paciente = Paciente()
    # campos que o validar da main lê (iguais aos do Extracao real, em app/schemas.py)
    medico_solicitante: MedicoSolicitante = Field(default_factory=MedicoSolicitante)
    cid_sugerido: str | None = None
    origem_cid: str | None = None
    cid_origem: str | None = None
    medicamentos: list = Field(default_factory=list)
    exames: list = Field(default_factory=list)
    evidencias: list = Field(default_factory=list)
    inconsistencias: list = Field(default_factory=list)


def extrator(**kw):
    return lambda texto: Ext(**kw)


GUIA = dict(tipo_documento="Guia de Solicitação de Procedimento")
TEXTO = "Paciente Maria. Solicito ressonância de joelho."
LAUDO_TEP = ("Paciente Maria. Angio-TC: falha de enchimento em artéria pulmonar compatível com "
             "TEP agudo. Conclusão: Tromboembolismo Pulmonar Agudo.")


# ---------------- H3.1.2 ----------------
def test_guia_de_rotina_do_pronto_socorro_vira_prioritario_e_nao_vai_para_revisao():
    e = triar(TEXTO, extrator(**GUIA), canal_origem="Pronto_Socorro")
    assert e["nivel_prioridade"] == "Prioritário" and e["sinal_prioridade"] == "canal Pronto_Socorro"
    assert e["classificacao"].nivel_prioridade == "Prioritário"
    assert e["destino"] == "Auditoria_Autorizacoes" and e["requer_revisao"] is False
    assert "Prioritário (canal Pronto_Socorro)" in e["justificativa"]


def test_pedido_com_cito_vira_prioritario():
    e = triar("Paciente Maria. CITO: ressonância de crânio.", extrator(**GUIA), canal_origem="Ambulatorio")
    assert e["nivel_prioridade"] == "Prioritário" and 'termo "CITO"' in e["sinal_prioridade"]


def test_score_baixo_do_pronto_socorro_mantem_prioritario_e_tambem_vai_a_revisao():
    e = triar(TEXTO, extrator(**GUIA, score_confianca_classificacao=0.5), canal_origem="Pronto_Socorro")
    assert e["nivel_prioridade"] == "Prioritário"
    assert e["destino"] == "Fila_Revisao_Humana" and e["requer_revisao"] is True
    assert "Prioridade Prioritário: canal Pronto_Socorro" in e["justificativa"]


def test_ilegivel_do_pronto_socorro_vai_a_revisao_mas_mantem_prioritario():
    leitor = lambda imgs: ("", NS(legivel=False, motivo="borrada"))
    e = triar("", extrator(), pdf_bytes=b"\x89PNG..", leitor=leitor, canal_origem="Pronto_Socorro")
    assert e["destino"] == "Fila_Revisao_Humana" and e["motivo_revisao"] == "ilegível"
    assert e["nivel_prioridade"] == "Prioritário"
    assert "Prioridade Prioritário" in e["justificativa"]


def test_ilegivel_de_rotina_mantem_o_texto_antigo_exato():
    leitor = lambda imgs: ("", NS(legivel=False, motivo="borrada"))
    e = triar("", extrator(), pdf_bytes=b"\x89PNG..", leitor=leitor, canal_origem="Balcao")
    assert e["nivel_prioridade"] == "Rotina"
    assert e["justificativa"] == "Enviado à revisão humana (regra R-REVISAO): ilegível."


def test_urgente_nao_e_rebaixado_pelo_canal():
    e = triar(TEXTO, extrator(**GUIA, nivel_prioridade="Urgente"), canal_origem="Pronto_Socorro")
    assert e["nivel_prioridade"] == "Urgente" and e["destino"] == "Fila_Emergencia_Medica"


# ---------------- H3.1.1 ----------------
def test_laudo_de_tep_vira_urgente_e_vai_para_emergencia_citando_o_achado():
    e = triar(LAUDO_TEP, extrator(tipo_documento="Laudo de Exame de Imagem",
                                  diagnostico_principal="Tromboembolismo Pulmonar Agudo (TEP)"),
              canal_origem="Ambulatorio")
    assert e["nivel_prioridade"] == "Urgente" and e["sinal_prioridade"] == "achado crítico: TEP"
    assert e["destino"] == "Fila_Emergencia_Medica" and e["regra"] == "R-URGENCIA"
    assert "achado crítico: Tromboembolismo Pulmonar Agudo (TEP)" in e["justificativa"]
    assert e["notificacao"]["canal"] == "Alerta_Plantao_Medico"


def test_achado_critico_vale_mesmo_que_o_llm_da_extracao_diga_rotina():
    e = triar(LAUDO_TEP, extrator(nivel_prioridade="Rotina"))
    assert e["nivel_prioridade"] == "Urgente" and e["classificacao"].nivel_prioridade == "Urgente"


def test_negacao_confirmada_pelo_llm_nao_vira_urgente():
    texto = "Paciente Maria. Angio-TC de tórax: ausência de sinais de TEP."
    chamar = lambda prompt: ('```json\n{"candidatos":[{"i":0,"estado":"negado",'
                             '"trecho_negacao":"ausência de sinais de TEP"}],"outros_achados":[]}\n```')
    e = triar(texto, extrator(tipo_documento="Laudo de Exame de Imagem"), confirmador=fazer_confirmador(chamar))
    assert e["nivel_prioridade"] == "Rotina" and e["destino"] == "Prontuario_Eletronico"


def test_llm_de_confirmacao_fora_do_ar_mantem_urgente():
    def cai(prompt):
        raise RuntimeError("503 UNAVAILABLE")
    texto = "Paciente Maria. Angio-TC de tórax: ausência de sinais de TEP."
    e = triar(texto, extrator(tipo_documento="Laudo de Exame de Imagem"), confirmador=fazer_confirmador(cai))
    assert e["nivel_prioridade"] == "Urgente" and e["destino"] == "Fila_Emergencia_Medica"


def test_json_quebrado_do_llm_mantem_urgente():
    e = triar("Paciente Maria. TEP agudo.", extrator(), confirmador=fazer_confirmador(lambda p: "isto não é json"))
    assert e["nivel_prioridade"] == "Urgente"


# ---------------- H3.1.3 ----------------
CENARIOS = [
    (TEXTO, extrator(), None),
    (TEXTO, extrator(**GUIA), "Pronto_Socorro"),
    ("Paciente Maria. CITO.", extrator(**GUIA), "Balcao"),
    (LAUDO_TEP, extrator(), "Balcao"),
    (TEXTO, extrator(score_confianca_classificacao=0.3), "Balcao"),
    (TEXTO, extrator(nivel_prioridade="Urgente"), "Balcao"),
]


@pytest.mark.parametrize("texto,ext,canal", CENARIOS)
def test_todo_documento_sai_com_exatamente_um_nivel_e_a_justificativa_traz_o_sinal(texto, ext, canal):
    e = triar(texto, ext, canal_origem=canal)
    assert e["nivel_prioridade"] in NIVEIS
    assert e["sinal_prioridade"]
    if not e["requer_revisao"] or e["nivel_prioridade"] != "Rotina":
        assert e["sinal_prioridade"].split(";")[0].split(" indicada")[0] in e["justificativa"] \
            or e["nivel_prioridade"] == "Urgente"


def test_rotina_sem_sinal_diz_nenhum_sinal():
    e = triar(TEXTO, extrator(), canal_origem="Balcao")
    assert e["nivel_prioridade"] == "Rotina" and e["sinal_prioridade"] == "nenhum sinal"
    assert "Rotina (nenhum sinal)" in e["justificativa"]