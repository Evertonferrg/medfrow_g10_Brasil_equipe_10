"""Decisão da auditora com dublês de armazenamento e do cálculo de destino."""

import json
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.rotas_decisao import get_colaboradores, router_decisao
from app.decisao import DecisaoAuditora
from app.eventos import ServicoEventos
from app.indice_revisao import IndiceRevisao
from app.revisao import (
    Colaboradores,
    CorrecaoInvalida,
    DecisaoConflito,
    SemDestinoCalculado,
    decidir_caso,
    prefixos_do_documento,
    validar_correcoes_basico,
)
from app.status import StatusDocumento as S


class Memoria:
    def __init__(self):
        self.dados = {}

    def ler(self, caminho):
        return self.dados.get(caminho)

    def salvar(self, caminho, conteudo):
        self.dados[caminho] = json.dumps(conteudo).encode()

    def mover(self, origem, destino):
        self.dados[destino] = self.dados.pop(origem)

    def existe(self, caminho):
        return caminho in self.dados

    def apagar(self, caminho):
        self.dados.pop(caminho, None)


def resultado(
    doc, crm="12345-XX", tipo="Receituário Médico", destino="Fila_Revisao_Humana"
):
    return {
        "status": "processado",
        "documento_id": doc,
        "classificacao": {
            "tipo_documento": tipo,
            "nivel_prioridade": "Rotina",
            "score_confianca_classificacao": 0.3,
        },
        "dados_extraidos": {
            "medico_solicitante": {"nome": "Dr. Carlos", "crm": crm},
            "paciente": {"nome": "Maria", "idade": 30, "data_nascimento": "12/03/1950"},
            "cid": "I26.9",
            "cid_sugerido": "I26.9",
        },
        "problemas": ["CRM em formato inválido"],
        "decisao_roteamento": {
            "destino_principal": destino,
            "requer_auditoria_humana": True,
            "justificativa_roteamento": "x",
            "regra_aplicada": "R-REVISAO",
        },
    }


@pytest.fixture
def amb(tmp_path):
    mem, ev, vistos = Memoria(), ServicoEventos(tmp_path), []

    def calcular(res):
        vistos.append(json.loads(json.dumps(res)))
        return (
            None
            if res["classificacao"]["tipo_documento"] == "Não identificado"
            else "Farmacia_Hospitalar"
        )

    colab = Colaboradores(mem, ev, calcular, validar_correcoes_basico)

    def entra(doc, **kw):
        mem.salvar(f"auditoria_humana/{doc}.json", resultado(doc, **kw))
        ev.registrar(doc, S.RECEBIDO)
        ev.registrar(doc, S.EM_AUDITORIA_HUMANA)

    return SimpleNamespace(mem=mem, ev=ev, colab=colab, vistos=vistos, entra=entra)


def aprovar(nome="Helena"):
    return DecisaoAuditora(acao="aprovar", auditora=nome)


def test_aprovar_leva_ao_destino_calculado_e_so_existe_em_processados(amb):
    amb.entra("A1")
    out = decidir_caso("A1", aprovar(), amb.colab)
    assert (
        out["destino"] == "Farmacia_Hospitalar"
        and out["caminho"] == "processados/rotina/A1.json"
    )
    assert prefixos_do_documento(amb.mem, "A1") == ["processados/rotina"]
    salvo = json.loads(amb.mem.ler(out["caminho"]))
    assert salvo["decisao_roteamento"]["destino_principal"] == "Farmacia_Hospitalar"
    assert salvo["decisao_roteamento"]["requer_auditoria_humana"] is False
    ultimo = amb.ev.listar("A1")[-1]
    assert ultimo["status"] == "processado" and ultimo["autor_nome"] == "Helena"
    assert amb.ev.verificar_cadeia("A1") == []


def test_caso_em_revisao_existe_so_em_auditoria_humana(amb):
    amb.entra("A2")
    assert prefixos_do_documento(amb.mem, "A2") == ["auditoria_humana"]


def test_segunda_aprovacao_da_conflito(amb):
    amb.entra("A3")
    decidir_caso("A3", aprovar(), amb.colab)
    with pytest.raises(DecisaoConflito):
        decidir_caso("A3", aprovar(), amb.colab)


def test_sem_destino_calculado_recusa_a_aprovacao(amb):
    amb.entra("A4", tipo="Não identificado")
    with pytest.raises(SemDestinoCalculado, match="sem destino calculado"):
        decidir_caso("A4", aprovar(), amb.colab)
    assert prefixos_do_documento(amb.mem, "A4") == ["auditoria_humana"]


def test_corrigir_crm_chega_ao_resultado_final_e_registra_antes_e_depois(amb):
    amb.entra("C1")
    d = DecisaoAuditora(
        acao="corrigir", auditora="Helena", correcoes={"crm": "123456-sp"}
    )
    out = decidir_caso("C1", d, amb.colab)
    salvo = json.loads(amb.mem.ler(out["caminho"]))
    assert salvo["dados_extraidos"]["medico_solicitante"]["crm"] == "123456-SP"
    assert (
        amb.vistos[-1]["dados_extraidos"]["medico_solicitante"]["crm"] == "123456-SP"
    )  # destino recalculado com o valor novo
    correcao = next(e for e in amb.ev.listar("C1") if e.get("campo") == "crm")
    assert (
        correcao["valor_anterior"],
        correcao["valor_novo"],
        correcao["autor_nome"],
    ) == ("12345-XX", "123456-SP", "Helena")


def test_crm_corrigido_para_valor_invalido_nao_altera_nada(amb):
    amb.entra("C2")
    antes = amb.mem.ler("auditoria_humana/C2.json")
    eventos_antes = amb.ev.listar("C2")
    d = DecisaoAuditora(
        acao="corrigir", auditora="Helena", correcoes={"crm": "99999-ZZ"}
    )
    with pytest.raises(CorrecaoInvalida) as e:
        decidir_caso("C2", d, amb.colab)
    assert e.value.campo == "crm"
    assert (
        amb.mem.ler("auditoria_humana/C2.json") == antes
        and amb.ev.listar("C2") == eventos_antes
    )


def test_correcao_de_campo_nao_editavel_ou_sem_mudanca_e_recusada(amb):
    amb.entra("C3")
    with pytest.raises(CorrecaoInvalida, match="não editável"):
        decidir_caso(
            "C3",
            DecisaoAuditora(acao="corrigir", auditora="H", correcoes={"destino": "x"}),
            amb.colab,
        )
    with pytest.raises(Exception, match="nenhum campo"):
        decidir_caso(
            "C3",
            DecisaoAuditora(acao="corrigir", auditora="H", correcoes={"cid": "i26.9"}),
            amb.colab,
        )


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("idade", "200"),
        ("idade", "abc"),
        ("data_nascimento", "31/02/2000"),
        ("cid", "XX"),
        ("paciente_nome", "x"),
    ],
)
def test_validacoes_basicas(campo, valor):
    with pytest.raises(CorrecaoInvalida):
        validar_correcoes_basico({"paciente": {}}, {campo: valor})


def test_rejeitar_vai_para_rejeitados_com_motivo(amb):
    amb.entra("R1")
    d = DecisaoAuditora(acao="rejeitar", auditora="Helena", motivo="documento ilegível")
    out = decidir_caso("R1", d, amb.colab)
    assert (
        prefixos_do_documento(amb.mem, "R1") == ["rejeitados"]
        and out["destino"] is None
    )
    ultimo = amb.ev.listar("R1")[-1]
    assert ultimo["status"] == "rejeitado" and "ilegível" in ultimo["detalhe"]


def test_redirecionar_so_para_destino_valido(amb):
    amb.entra("D1")
    with pytest.raises(Exception, match="destino inválido"):
        decidir_caso(
            "D1",
            DecisaoAuditora(
                acao="redirecionar", auditora="H", destino="Fila_Revisao_Humana"
            ),
            amb.colab,
        )
    out = decidir_caso(
        "D1",
        DecisaoAuditora(
            acao="redirecionar", auditora="H", destino="Prontuario_Eletronico"
        ),
        amb.colab,
    )
    assert out["destino"] == "Prontuario_Eletronico"


def test_urgente_vai_para_processados_urgentes(amb):
    amb.entra("U1")
    amb.colab.calcular_destino = lambda res: "Fila_Emergencia_Medica"
    assert (
        decidir_caso("U1", aprovar(), amb.colab)["caminho"]
        == "processados/urgentes/U1.json"
    )


def test_caso_decidido_sai_da_fila_de_revisao_em_menos_de_2s(amb):
    amb.entra("F1")
    amb.entra("F2")
    indice = IndiceRevisao(
        amb.ev,
        carregar=lambda doc: json.loads(
            amb.mem.ler(f"auditoria_humana/{doc}.json") or "null"
        ),
    )
    assert {c.documento_id for c in indice.listar_casos_revisao()} == {"F1", "F2"}
    t = time.perf_counter()
    decidir_caso("F1", aprovar(), amb.colab)
    assert [c.documento_id for c in indice.listar_casos_revisao()] == ["F2"]
    assert time.perf_counter() - t < 2


def _cliente(amb):
    app = FastAPI()
    app.include_router(router_decisao)
    app.dependency_overrides[get_colaboradores] = lambda: amb.colab
    return TestClient(app)


def test_rota_aprovar_404_409_e_422(amb):
    c = _cliente(amb)
    amb.entra("H1")
    assert (
        c.post(
            "/documentos/NAO-EXISTE/decisao", json={"acao": "aprovar", "auditora": "H"}
        ).status_code
        == 404
    )
    assert (
        c.post(
            "/documentos/H1/decisao", json={"acao": "aprovar", "auditora": "H"}
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/documentos/H1/decisao", json={"acao": "aprovar", "auditora": "H"}
        ).status_code
        == 409
    )
    amb.entra("H2")
    r = c.post(
        "/documentos/H2/decisao",
        json={"acao": "corrigir", "auditora": "H", "correcoes": {"crm": "1-ZZ"}},
    )
    assert r.status_code == 422 and "crm" in r.json()["detail"]
    assert (
        c.post(
            "/documentos/a.b/decisao", json={"acao": "aprovar", "auditora": "H"}
        ).status_code
        == 400
    )


def test_decisao_apaga_o_estado_auxiliar_da_revisao(amb):
    amb.entra("E1")
    amb.mem.salvar(
        "auditoria_humana/E1.estado.json", {"destino_calculado": "Farmacia_Hospitalar"}
    )
    decidir_caso("E1", aprovar(), amb.colab)
    assert not amb.mem.existe("auditoria_humana/E1.estado.json")
    assert prefixos_do_documento(amb.mem, "E1") == ["processados/rotina"]


def test_sobrepor_correcoes_so_toca_em_chaves_existentes_e_nao_muda_a_entrada():
    from app.revisao import sobrepor_correcoes

    extracao = {
        "medico_solicitante": {"nome": "A", "crm": "x"},
        "paciente": {"nome": "M"},
        "cid_sugerido": "I26.9",
    }
    dados = {
        "medico_solicitante": {"crm": "CRM-SP 123456"},
        "paciente": {"idade": 40},
        "cid_sugerido": "S72.0",
        "cid": "S72.0",
    }
    novo = sobrepor_correcoes(extracao, dados)
    assert novo["medico_solicitante"]["crm"] == "CRM-SP 123456"
    assert "idade" not in novo["paciente"]  # chave que a extração não tem
    assert novo["cid_sugerido"] == "S72.0" and "cid" not in novo
    assert extracao["medico_solicitante"]["crm"] == "x"


def test_rejeitar_sem_motivo_ou_so_com_espacos_e_recusado():
    for motivo in (None, "", "   "):
        with pytest.raises(ValueError, match="motivo"):
            DecisaoAuditora(acao="rejeitar", auditora="H", motivo=motivo)


def test_motivo_da_rejeicao_aparece_no_resultado_e_nao_gera_destino(amb):
    amb.entra("J1")
    out = decidir_caso(
        "J1",
        DecisaoAuditora(acao="rejeitar", auditora="H", motivo="CRM ilegível"),
        amb.colab,
    )
    assert out["destino"] is None and out["caminho"] == "rejeitados/J1.json"
    salvo = json.loads(amb.mem.ler(out["caminho"]))
    rot = salvo["decisao_roteamento"]
    assert "CRM ilegível" in rot["justificativa_roteamento"]
    assert rot["requer_auditoria_humana"] is False
    assert not amb.vistos  # nenhum cálculo de destino: não passa por rotear


def test_redirecionar_registra_justificativa_da_auditora_e_a_mudanca_na_trilha(amb):
    amb.entra("K1")
    d = DecisaoAuditora(
        acao="redirecionar", auditora="Helena", destino="Prontuario_Eletronico"
    )
    out = decidir_caso("K1", d, amb.colab)
    salvo = json.loads(amb.mem.ler(out["caminho"]))
    assert salvo["decisao_roteamento"]["justificativa_roteamento"].startswith(
        "Destino definido pela auditora"
    )
    assert salvo["decisao_roteamento"]["destino_principal"] == "Prontuario_Eletronico"
    mudanca = next(e for e in amb.ev.listar("K1") if e.get("campo") == "destino")
    assert (
        mudanca["valor_anterior"] == "Farmacia_Hospitalar"
    )  # o que o roteamento escolheria
    assert mudanca["valor_novo"] == "Prontuario_Eletronico"
    assert amb.ev.verificar_cadeia("K1") == []


def test_redirecionar_para_emergencia_alerta_o_plantao(amb):
    amb.entra("L1")
    alertas = []
    amb.colab.alertar_plantao = alertas.append
    d = DecisaoAuditora(
        acao="redirecionar", auditora="H", destino="Fila_Emergencia_Medica"
    )
    out = decidir_caso("L1", d, amb.colab)
    assert (
        out["plantao_alertado"] is True
        and out["caminho"] == "processados/urgentes/L1.json"
    )
    assert len(alertas) == 1 and alertas[0]["documento_id"] == "L1"


def test_redirecionar_para_outro_destino_nao_alerta(amb):
    amb.entra("L2")
    alertas = []
    amb.colab.alertar_plantao = alertas.append
    decidir_caso(
        "L2",
        DecisaoAuditora(
            acao="redirecionar", auditora="H", destino="Farmacia_Hospitalar"
        ),
        amb.colab,
    )
    assert alertas == []


def test_falha_no_alerta_nao_desfaz_a_decisao(amb):
    amb.entra("L3")

    def quebra(_resultado):
        raise RuntimeError("slack fora do ar")

    amb.colab.alertar_plantao = quebra
    d = DecisaoAuditora(
        acao="redirecionar", auditora="H", destino="Fila_Emergencia_Medica"
    )
    out = decidir_caso("L3", d, amb.colab)
    assert out["plantao_alertado"] is False
    assert prefixos_do_documento(amb.mem, "L3") == ["processados/urgentes"]
    assert amb.ev.status_atual("L3") == S.PROCESSADO


def test_rota_rejeitar_sem_motivo_da_422_e_com_motivo_move(amb):
    c = _cliente(amb)
    amb.entra("M1")
    r = c.post("/documentos/M1/decisao", json={"acao": "rejeitar", "auditora": "H"})
    assert r.status_code == 422
    assert prefixos_do_documento(amb.mem, "M1") == ["auditoria_humana"]
    ok = c.post(
        "/documentos/M1/decisao",
        json={"acao": "rejeitar", "auditora": "H", "motivo": "ilegível"},
    )
    assert ok.status_code == 200 and prefixos_do_documento(amb.mem, "M1") == [
        "rejeitados"
    ]
    destino_fora = c.post(
        "/documentos/M1/decisao",
        json={"acao": "redirecionar", "auditora": "H", "destino": "Lugar_Nenhum"},
    )
    assert destino_fora.status_code in (409, 422)
