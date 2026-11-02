"""H3.3.1 — alerta ao plantão (sem LLM, sem rede)."""
from types import SimpleNamespace

import pytest

from app import grafo as g
from app.alerta import LIMITE_MENSAGEM, gerar_alerta, montar_mensagem_alerta


# ---------- mensagem (função pura) ----------

def test_laudo_de_tep_do_edital_cita_achado_paciente_e_origem():
    msg = montar_mensagem_alerta("Laudo critico de TEP Agudo", "Carlos Eduardo Mendes", "Pronto_Socorro")
    assert msg == ("ALERTA URGENTE: Laudo critico de TEP Agudo para paciente "
                   "Carlos Eduardo Mendes no Pronto-Socorro.")


def test_sem_origem_omite_o_local():
    msg = montar_mensagem_alerta("TEP", "Ana", None)
    assert msg == "ALERTA URGENTE: TEP para paciente Ana."


def test_sem_paciente_nao_quebra():
    assert "não identificado" in montar_mensagem_alerta("TEP", None, "Balcao")


@pytest.mark.parametrize("tamanho", [150, 200, 500, 5000])
def test_mensagem_nunca_passa_de_200_caracteres(tamanho):
    msg = montar_mensagem_alerta("A" * tamanho, "Maria", "Pronto_Socorro")
    assert len(msg) <= LIMITE_MENSAGEM
    assert msg.startswith("ALERTA URGENTE")


def test_gerar_alerta_devolve_canal_e_mensagem():
    n = gerar_alerta("TEP", "Ana", "Pronto_Socorro")
    assert n.canal == "Alerta_Plantao_Medico"
    assert "TEP" in n.mensagem and "Ana" in n.mensagem


# ---------- grafo ----------

class FakeDecisao:
    """Dublê de DecisaoRoteamento (isola o teste do roteamento real)."""
    def __init__(self, regra, revisao=False, notificacao=None):
        self.destino_principal = "Fila_Emergencia_Medica" if regra == "R-URGENCIA" else "Prontuario_Eletronico"
        self.regra_aplicada = regra
        self.requer_auditoria_humana = revisao
        self.justificativa_roteamento = "x"
        self.notificacao_gerada = notificacao

    def model_copy(self, update):
        nova = FakeDecisao(self.regra_aplicada, self.requer_auditoria_humana, self.notificacao_gerada)
        for k, v in update.items():
            setattr(nova, k, v)
        return nova


def extracao(nivel="Urgente", tipo="Laudo de Exame de Imagem", diag="TEP Agudo"):
    return SimpleNamespace(tipo_documento=tipo, especialidade="Pneumologia", nivel_prioridade=nivel,
                           diagnostico_principal=diag,
                           paciente=SimpleNamespace(nome="Carlos Eduardo Mendes"))


@pytest.fixture
def amb(monkeypatch):
    cfg = {"aval": SimpleNamespace(nivel="Urgente", sinal="achado crítico: TEP", achado="TEP Agudo")}
    monkeypatch.setattr(g.config, "limite_confianca", lambda: 0.7)
    monkeypatch.setattr(g.config, "ARQUIVO_REGRAS", "x.json", raising=False)
    monkeypatch.setattr(g, "carregar_regras", lambda a: [])
    monkeypatch.setattr(g, "validar", lambda e, t: (e, [], 0.95))
    monkeypatch.setattr(g, "avaliar_urgencia", lambda *a, **k: cfg["aval"])
    monkeypatch.setattr(
        g.rt, "criar_decisao_roteamento",
        lambda s, **kw: FakeDecisao("R-URGENCIA" if s["nivel_prioridade"] == "Urgente" else "R-PRONTUARIO"))
    monkeypatch.setattr(g, "montar_resposta", lambda d, s: SimpleNamespace(
        model_dump=lambda mode="json": {"notificacao": s.get("notificacao"), "destino": s.get("destino")}))
    return cfg


def test_laudo_urgente_gera_alerta_com_tep_paciente_e_pronto_socorro(amb):
    r = g.triar("laudo", extrator=lambda t: extracao(), canal_origem="Pronto_Socorro",
                classificador=lambda e, sc: None)
    msg = r["notificacao"]["mensagem"]
    assert r["notificacao"]["canal"] == "Alerta_Plantao_Medico"
    assert "ALERTA URGENTE" in msg and "TEP" in msg
    assert "Carlos Eduardo Mendes" in msg and "Pronto-Socorro" in msg
    assert len(msg) <= 200


def test_alerta_tambem_vai_para_a_decisao_de_roteamento(amb):
    r = g.triar("laudo", extrator=lambda t: extracao(), canal_origem="Pronto_Socorro",
                classificador=lambda e, sc: None)
    assert "TEP" in r["decisao_roteamento"].notificacao_gerada.mensagem


def test_documento_de_rotina_nao_gera_alerta(amb):
    amb["aval"] = SimpleNamespace(nivel="Rotina", sinal="nenhum sinal", achado=None)
    r = g.triar("receita", extrator=lambda t: extracao(nivel="Rotina", tipo="Receituário Médico"),
                classificador=lambda e, sc: None)
    assert r.get("notificacao") is None
    assert r["decisao_roteamento"].notificacao_gerada is None


def test_achado_enorme_no_grafo_continua_com_ate_200_caracteres(amb):
    amb["aval"] = SimpleNamespace(nivel="Urgente", sinal="x", achado="B" * 1000)
    r = g.triar("laudo", extrator=lambda t: extracao(), canal_origem="Pronto_Socorro",
                classificador=lambda e, sc: None)
    assert len(r["notificacao"]["mensagem"]) <= 200