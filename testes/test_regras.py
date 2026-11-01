import pytest

from app import storage
from app.grafo import triar
from app.roteamento import decidir_destino
from app.schemas import Evidencia, Exame, Medicamento, Medico
from app.validacao import normalizar_crm, validar
from testes.conftest import (
    GUIA,
    LAUDO_TEP,
    RECEITA,
    extracao,
    extrator_fixo,
    extrator_que_quebra,
)


# ---- H2.1.x: roteamento (função pura) ----
@pytest.mark.parametrize(
    "tipo,prio,rev,esperado",
    [
        ("Receituário Médico", "Rotina", False, ("Farmacia_Hospitalar", "R-RECEITA")),
        (
            "Guia de Solicitação de Procedimento",
            "Rotina",
            False,
            ("Auditoria_Autorizacoes", "R-GUIA"),
        ),
        (
            "Laudo de Exame de Imagem",
            "Rotina",
            False,
            ("Prontuario_Eletronico", "R-PRONTUARIO"),
        ),
        (
            "Relatório de Alta",
            "Rotina",
            False,
            ("Prontuario_Eletronico", "R-PRONTUARIO"),
        ),
        ("Atestado Médico", "Rotina", False, ("Prontuario_Eletronico", "R-PRONTUARIO")),
        (
            "Receituário Médico",
            "Urgente",
            False,
            ("Fila_Emergencia_Medica", "R-URGENCIA"),
        ),  # urgência vence rotina
        (
            "Receituário Médico",
            "Urgente",
            True,
            ("Fila_Revisao_Humana", "R-REVISAO"),
        ),  # revisão vence tudo
    ],
)
def test_decidir_destino(tipo, prio, rev, esperado):
    assert decidir_destino(tipo, prio, rev) == esperado


# ---- H2.1.1 a H2.1.3 + H2.2.1: pelo grafo completo ----
def test_receita_vai_para_farmacia_com_medicamentos_estruturados():
    e = extracao(
        tipo_documento="Receituário Médico",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.93,
        paciente={"nome": "Maria Souza"},
        medico_solicitante=Medico(nome="Dr. Paulo Lima", crm="CRM 99887 SP"),
        diagnostico_principal=None,
        cid_sugerido=None,
        medicamentos=[
            Medicamento(
                nome="Amoxicilina", dose="500mg", frequencia="8/8h", duracao="7 dias"
            )
        ],
    )
    s = triar(RECEITA, extrator_fixo(e))
    assert s["destino"] == "Farmacia_Hospitalar" and s["requer_revisao"] is False
    assert s["extracao"].medicamentos[0].dose == "500mg"
    assert (
        "Receituário Médico" in s["justificativa"] and "R-RECEITA" in s["justificativa"]
    )


def test_guia_vai_para_auditoria_com_exames_e_tuss():
    e = extracao(
        tipo_documento="Guia de Solicitação de Procedimento",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.9,
        paciente={"nome": "Joao Pereira"},
        medico_solicitante=Medico(nome="Dra. Ana Torres", crm="CRM-RJ 55443"),
        diagnostico_principal=None,
        cid_sugerido=None,
        exames=[Exame(nome="Ressonancia de joelho", codigo_tuss="40801020")],
    )
    s = triar(GUIA, extrator_fixo(e))
    assert s["destino"] == "Auditoria_Autorizacoes"
    assert s["extracao"].exames[0].codigo_tuss == "40801020"


def test_urgencia_tem_precedencia_e_gera_alerta():
    s = triar(LAUDO_TEP, extrator_fixo(extracao()))
    assert (
        s["destino"] == "Fila_Emergencia_Medica"
        and s["notificacao"]["canal"] == "Alerta_Plantao_Medico"
    )


def test_revisao_justificativa_diz_a_duvida():
    e = extracao(nivel_prioridade="Rotina", score_confianca_classificacao=0.5)
    s = triar(LAUDO_TEP, extrator_fixo(e))
    assert s["destino"] == "Fila_Revisao_Humana"
    assert "R-REVISAO" in s["justificativa"]


def test_urgencia_duvidosa_vai_para_revisao_mas_alerta_o_plantao():
    e = extracao(
        medico_solicitante=Medico(nome="Dra. Renata Silveira", crm=None)
    )  # sem CRM
    s = triar(LAUDO_TEP, extrator_fixo(e))
    assert s["destino"] == "Fila_Revisao_Humana"
    assert s["notificacao"]["canal"] == "Alerta_Plantao_Medico"


def test_falha_do_llm_vai_para_revisao():
    s = triar(LAUDO_TEP, extrator_que_quebra)
    assert (
        s["destino"] == "Fila_Revisao_Humana"
        and "Gemini fora do ar" in s["justificativa"]
    )


# ---- H1.3.x: validação anti-alucinação ----
def test_crm_normalizado():
    assert normalizar_crm("CRM-SP 145892") == "145892-SP"
    assert normalizar_crm("CRM 99887 SP") == "99887-SP"
    assert normalizar_crm("CRM-XX 145892") is None  # UF inexistente


def test_documento_sem_crm_nunca_recebe_valor_plausivel():
    ext, probs, _ = validar(
        extracao(
            medico_solicitante=Medico(nome="Dra. Renata Silveira", crm="CRM-SP 777777")
        ),
        LAUDO_TEP,
    )  # 777777 não está no texto
    assert ext.medico_solicitante.crm is None
    assert any("não consta no texto" in p for p in probs)


def test_medicamento_inventado_e_descartado():
    e = extracao(
        tipo_documento="Receituário Médico",
        medicamentos=[
            Medicamento(nome="Amoxicilina", dose="500mg"),
            Medicamento(nome="Morfina", dose="10mg"),
        ],
    )
    ext, probs, _ = validar(e, RECEITA)
    assert [m.nome for m in ext.medicamentos] == ["Amoxicilina"]
    assert any("Morfina" in p for p in probs)


def test_medicamento_sem_dose_e_sinalizado():
    e = extracao(
        tipo_documento="Receituário Médico",
        medicamentos=[Medicamento(nome="Amoxicilina")],
    )
    _, probs, _ = validar(e, RECEITA)
    assert any("sem dose" in p for p in probs)


def test_tuss_inventado_removido_e_exames_duplicados_unificados():
    e = extracao(
        exames=[
            Exame(nome="Ressonancia de joelho", codigo_tuss="99999999"),
            Exame(nome="ressonancia de joelho"),
        ]
    )
    ext, _probs, _ = validar(e, GUIA)
    assert len(ext.exames) == 1 and ext.exames[0].codigo_tuss is None


def test_nome_inteiro_nao_casa_pedaco_de_palavra():
    _ext, probs, _ = validar(
        extracao(paciente={"nome": "Ana"}), "Paciente: Mariana Costa"
    )
    assert any("não encontrado" in p for p in probs)


def test_cid_escrito_no_documento_vira_origem_escrito():
    ext, _, _ = validar(extracao(), LAUDO_TEP + " CID I26.9")
    assert ext.cid_origem == "escrito"


def test_evidencia_inexistente_e_descartada():
    e = extracao(
        evidencias=[
            Evidencia(campo="paciente", trecho="Paciente: Carlos Eduardo Mendes"),
            Evidencia(campo="crm", trecho="CRM-SP 000000"),
        ]
    )
    ext, _, _ = validar(e, LAUDO_TEP)
    assert [ev.campo for ev in ext.evidencias] == ["paciente"]


# ---- storage ----
def test_storage_bloqueia_path_traversal():
    with pytest.raises(ValueError):
        storage.salvar("../fora.txt", "x")
    with pytest.raises(ValueError):
        storage.salvar("/abs/x.txt", "x")


def test_oci_falhou_salva_no_disco(monkeypatch):
    monkeypatch.setenv("OCI_NAMESPACE", "ns")
    monkeypatch.setattr(
        storage,
        "_salvar_oci",
        lambda *a: (_ for _ in ()).throw(RuntimeError("sem rede")),
    )
    r = storage.salvar("recebidos/X-1.txt", "dado")
    assert r["local"] == "disco" and r["status_backup"].startswith(
        "oci_falhou_salvo_local"
    )
    assert storage._local("recebidos/X-1.txt").read_text() == "dado"
