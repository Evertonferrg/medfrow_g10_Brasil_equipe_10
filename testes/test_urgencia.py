"""H3.1.1 T7, H3.1.2 T4, H3.1.3 T5 — lógica de urgência (sem LLM real)."""
import pytest

from app.urgencia import (Avaliacao, NivelPrioridade as N, avaliar_urgencia, buscar_candidatos,
                          carregar_regras, maximo, montar_prompt, normalizar, ordem)

REGRAS = carregar_regras()          # padrões embutidos + config/regras.json, se existir

# H3.1.1 T6: um laudo sintético por achado da lista
LAUDOS_CRITICOS = {
    "TEP": "Angio-TC de tórax: falha de enchimento em artéria pulmonar direita compatível com TEP agudo.",
    "IAM": "ECG com supradesnivelamento de ST em parede anterior, compatível com IAM em evolução.",
    "AVC": "Ressonância de crânio: restrição à difusão em território da ACM esquerda, AVC isquêmico agudo.",
    "Sepse": "Paciente com hipotensão refratária e lactato elevado, quadro de choque séptico.",
    "Dissecção de aorta": "Angio-TC: flap intimal em aorta ascendente, dissecção aguda de aorta tipo A.",
    "Hemorragia intracraniana": "TC de crânio sem contraste: hemorragia intracraniana frontal direita com desvio de linha média.",
}
NEGADOS = [
    ("Angio-TC de tórax: ausência de sinais de TEP.", "ausência de sinais de TEP"),
    ("TC de crânio normal, sem evidência de hemorragia intracraniana.", "sem evidência de hemorragia intracraniana"),
]


def confirmador_que_nega(texto, candidatos, citacao):
    return {"candidatos": [{"i": i, "estado": "negado", "trecho_negacao": citacao}
                           for i in range(len(candidatos))], "outros_achados": []}


# ---------- H3.1.3: ordem e obrigatoriedade ----------
def test_ordem_dos_niveis():
    assert ordem("Rotina") < ordem("Prioritário") < ordem("Urgente")
    assert maximo("Rotina", "Urgente", "Prioritário") == N.URGENTE
    with pytest.raises(ValueError):
        ordem("Qualquer")


@pytest.mark.parametrize("texto,canal", [("", None), ("Consulta de rotina, sem queixas.", "Balcao"),
                                          ("texto qualquer", "Pronto_Socorro")])
def test_todo_documento_sai_com_exatamente_um_nivel_e_um_sinal(texto, canal):
    a = avaliar_urgencia(texto, canal, None, REGRAS)
    assert isinstance(a, Avaliacao) and a.nivel in set(N) and a.sinal


def test_sem_nenhum_sinal_e_rotina_explicito():
    a = avaliar_urgencia("Receita de rotina: losartana 50mg.", "Balcao", "Rotina", REGRAS)
    assert (a.nivel, a.sinal) == (N.ROTINA, "nenhum sinal")


# ---------- H3.1.1: achados críticos ----------
@pytest.mark.parametrize("achado", list(LAUDOS_CRITICOS))
def test_sensibilidade_100_por_cento_nos_laudos_com_achado(achado):
    a = avaliar_urgencia(LAUDOS_CRITICOS[achado], "Balcao", "Rotina", REGRAS)
    assert a.nivel == N.URGENTE
    assert a.sinal == f"achado crítico: {achado}"
    assert a.trecho


def test_acento_e_caixa_nao_atrapalham():
    a = avaliar_urgencia("TROMBOEMBOLISMO PULMONAR AGUDO bilateral", None, None, REGRAS)
    assert a.nivel == N.URGENTE
    assert normalizar("Embolia Pulmonar") == "embolia pulmonar" and len(normalizar("çãé")) == 3


@pytest.mark.parametrize("texto", ["Paciente tépido, sem queixas.", "Citoplasma sem alterações.",
                                    "Relatório de manutenção do equipamento."])
def test_palavra_inteira_evita_falso_positivo(texto):
    assert avaliar_urgencia(texto, None, None, REGRAS).nivel == N.ROTINA


def test_trecho_guardado_mostra_o_contexto():
    c = buscar_candidatos(LAUDOS_CRITICOS["TEP"], REGRAS["achados_criticos"])
    assert c and "TEP" in c[0].trecho


# ---------- H3.1.1 T3: negação com confirmação do LLM ----------
@pytest.mark.parametrize("texto,citacao", NEGADOS)
def test_negacao_explicita_confirmada_pelo_llm_nao_e_urgente(texto, citacao):
    a = avaliar_urgencia(texto, "Balcao", "Rotina", REGRAS,
                         confirmador=lambda t, c: confirmador_que_nega(t, c, citacao))
    assert a.nivel == N.ROTINA and "negação" in a.sinal


def test_sem_confirmador_a_negacao_continua_urgente():
    assert avaliar_urgencia(NEGADOS[0][0], None, None, REGRAS).nivel == N.URGENTE


def test_citacao_inventada_pelo_llm_nao_rebaixa():
    a = avaliar_urgencia(NEGADOS[0][0], None, None, REGRAS,
                         confirmador=lambda t, c: confirmador_que_nega(t, c, "frase que não existe no laudo"))
    assert a.nivel == N.URGENTE


def test_negado_sem_citacao_nao_rebaixa():
    a = avaliar_urgencia(NEGADOS[0][0], None, None, REGRAS,
                         confirmador=lambda t, c: {"candidatos": [{"i": 0, "estado": "negado", "trecho_negacao": ""}]})
    assert a.nivel == N.URGENTE


def test_suspeita_continua_urgente():
    a = avaliar_urgencia("Suspeita de TEP, correlacionar com clínica.", None, None, REGRAS,
                         confirmador=lambda t, c: {"candidatos": [{"i": 0, "estado": "suspeito"}]})
    assert a.nivel == N.URGENTE


def test_se_um_candidato_e_negado_e_outro_afirmado_continua_urgente():
    texto = "Sem sinais de TEP à direita. Presença de TEP à esquerda."
    a = avaliar_urgencia(texto, None, None, REGRAS, confirmador=lambda t, c: {"candidatos": [
        {"i": 0, "estado": "negado", "trecho_negacao": "Sem sinais de TEP à direita"},
        {"i": 1, "estado": "afirmado"}]})
    assert a.nivel == N.URGENTE


def test_llm_fora_do_ar_mantem_urgente_e_avisa():
    def cai(t, c):
        raise RuntimeError("503 UNAVAILABLE")
    a = avaliar_urgencia(NEGADOS[0][0], None, None, REGRAS, confirmador=cai)
    assert a.nivel == N.URGENTE and a.motivos_revisao


def test_llm_aponta_achado_escrito_de_outra_forma():
    a = avaliar_urgencia("Paciente com oclusão de artéria cerebral média em evolução.", None, "Rotina", REGRAS,
                         confirmador=lambda t, c: {"candidatos": [], "outros_achados": ["AVC isquêmico"]})
    assert a.nivel == N.URGENTE and "AVC isquêmico" in a.sinal


def test_prompt_cita_os_trechos():
    c = buscar_candidatos(LAUDOS_CRITICOS["TEP"], REGRAS["achados_criticos"])
    p = montar_prompt(LAUDOS_CRITICOS["TEP"], c)
    assert "[TEP]" in p and "JSON" in p


# ---------- H3.1.2: piso de prioridade ----------
def test_guia_de_rotina_vinda_do_pronto_socorro_vira_prioritario():
    a = avaliar_urgencia("Guia de ressonância de joelho.", "Pronto_Socorro", "Rotina", REGRAS)
    assert (a.nivel, a.sinal) == (N.PRIORITARIO, "canal Pronto_Socorro")


@pytest.mark.parametrize("termo", ["CITO", "urgente", "Urgência", "emergência", "imediato"])
def test_termo_de_urgencia_no_texto_vira_prioritario(termo):
    a = avaliar_urgencia(f"Solicito ressonância {termo} por dor intensa.", "Balcao", "Rotina", REGRAS)
    assert a.nivel == N.PRIORITARIO and normalizar(termo)[:4] in normalizar(a.sinal)


def test_elevar_nunca_rebaixa_um_urgente():
    a = avaliar_urgencia("Pedido urgente.", "Pronto_Socorro", "Urgente", REGRAS)
    assert a.nivel == N.URGENTE


def test_canal_prioritario_e_termo_juntos_listam_os_dois_sinais():
    a = avaliar_urgencia("Pedido urgente.", "Pronto_Socorro", "Rotina", REGRAS)
    assert a.nivel == N.PRIORITARIO and "canal Pronto_Socorro" in a.sinal and "urgente" in a.sinal


def test_documento_ilegivel_do_pronto_socorro_ainda_sobe_para_prioritario():
    """Score baixo/ilegível não impede o piso: o texto vazio ainda é avaliado pelo canal."""
    assert avaliar_urgencia("", "Pronto_Socorro", None, REGRAS).nivel == N.PRIORITARIO
