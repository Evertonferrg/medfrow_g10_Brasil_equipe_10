"""H1.3.4: medicamentos e posologia."""

import pytest
from fastapi.testclient import TestClient

from app.api import criar_app
from app.llm import PROMPT
from app.schemas import Extracao, Medicamento, Medico, Paciente
from app.validacao import precisa_revisao, validar
from testes.fixtures import receitas as R


def ext(medicamentos, tipo="Receituário Médico") -> Extracao:
    return Extracao(
        tipo_documento=tipo,
        especialidade="Clínica Geral",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.95,
        paciente=Paciente(nome="Maria Souza"),
        medico_solicitante=Medico(nome="Dr. Paulo Lima", crm="CRM 100001 SP"),
        medicamentos=[Medicamento(**m) for m in medicamentos],
    )


def nomes(e):
    return [m.nome for m in e.medicamentos]


# ---------------- critérios de aceite ----------------
@pytest.mark.parametrize(
    "texto,qtd",
    [(R.RECEITA_1, 1), (R.RECEITA_3, 3), (R.RECEITA_5, 5)],
    ids=["1-medicamento", "3-medicamentos", "5-medicamentos"],
)
def test_receita_gera_um_item_por_medicamento(texto, qtd):
    itens = {
        1: R.ITENS_RECEITA_3[:1],
        3: R.ITENS_RECEITA_3,
        5: R.ITENS_RECEITA_3
        + [
            {
                "nome": "Ibuprofeno",
                "dose": "600mg",
                "via": "via oral",
                "frequencia": "de 12 em 12 horas",
                "duracao": "5 dias",
            },
            {
                "nome": "Loratadina",
                "dose": "10mg",
                "via": "via oral",
                "frequencia": "1 vez ao dia",
                "duracao": "10 dias",
            },
        ],
    }[qtd]
    e, problemas, score = validar(ext(itens), texto)
    assert len(e.medicamentos) == qtd and problemas == [] and score == 0.95


def test_tres_medicamentos_cada_um_com_a_dose_certa():
    e, _, _ = validar(ext(R.ITENS_RECEITA_3), R.RECEITA_3)
    assert {m.nome: m.dose for m in e.medicamentos} == {
        "Amoxicilina": "500mg",
        "Dipirona": "1g",
        "Omeprazol": "20mg",
    }


def test_medicamento_sem_dose_fica_vazio_e_o_documento_e_sinalizado():
    e, problemas, score = validar(
        ext([{"nome": "Amoxicilina", "via": "via oral"}]), R.RECEITA_SEM_DOSE
    )
    assert e.medicamentos[0].dose is None
    assert any(p.startswith("campo faltante: dose") for p in problemas)
    assert precisa_revisao(score, problemas)


def test_medicamento_sem_dose_fora_de_receita_nao_e_cobrado():
    texto = "LAUDO. Paciente: Maria Souza. Dr. Paulo Lima CRM 100001 SP. Em uso de Amoxicilina."
    _, problemas, _ = validar(
        ext([{"nome": "Amoxicilina"}], tipo="Laudo de Exame de Imagem"), texto
    )
    assert not any("campo faltante" in p for p in problemas)


# ---------------- dose: nunca um valor que não está escrito ----------------
def test_dose_com_espaco_no_documento_e_aceita():
    texto = R.CABECALHO + "1) Amoxicilina 500 mg, via oral."
    e, problemas, _ = validar(ext([{"nome": "Amoxicilina", "dose": "500mg"}]), texto)
    assert e.medicamentos[0].dose == "500mg" and problemas == []


@pytest.mark.parametrize(
    "dose_do_modelo,no_texto",
    [
        ("500mg", "50mg"),  # dose trocada
        ("5mg", "25mg"),  # pedaço de outro número
        ("5mg", "1,5mg"),  # parte de um decimal
        ("0,5g", "500mg"),  # outra unidade: não converte
    ],
    ids=["trocada", "pedaco-de-numero", "decimal", "outra-unidade"],
)
def test_dose_que_nao_esta_escrita_e_descartada(dose_do_modelo, no_texto):
    texto = R.CABECALHO + f"1) Amoxicilina {no_texto}, via oral."
    e, problemas, _ = validar(
        ext([{"nome": "Amoxicilina", "dose": dose_do_modelo}]), texto
    )
    assert e.medicamentos[0].dose is None
    assert any(p.startswith("campo não confirmado no texto: dose") for p in problemas)
    assert not any("campo faltante" in p for p in problemas)  # não conta duas vezes


def test_dose_de_outro_medicamento_nao_vale():
    # o modelo deu a dose da Dipirona (1g) para a Amoxicilina
    e, problemas, _ = validar(
        ext(
            [{"nome": "Amoxicilina", "dose": "1g"}, {"nome": "Dipirona", "dose": "1g"}]
        ),
        R.RECEITA_3,
    )
    por_nome = {m.nome: m.dose for m in e.medicamentos}
    assert por_nome == {"Amoxicilina": None, "Dipirona": "1g"} and problemas


# ---------------- via, frequência e duração ----------------
def test_via_escrita_e_mantida_e_via_deduzida_e_descartada():
    texto = R.CABECALHO + "1) Amoxicilina 500mg, 1 comprimido de 8 em 8 horas."
    e, problemas, _ = validar(
        ext([{"nome": "Amoxicilina", "dose": "500mg", "via": "oral"}]), texto
    )
    assert e.medicamentos[0].via is None  # 'comprimido' não prova a via
    assert any("via" in p and "não confirmado" in p for p in problemas)
    e2, p2, _ = validar(
        ext([{"nome": "Amoxicilina", "dose": "500mg", "via": "via oral"}]), R.RECEITA_1
    )
    assert e2.medicamentos[0].via == "via oral" and p2 == []


def test_frequencia_abreviada_e_aceita_mas_numero_inventado_nao():
    e, p, _ = validar(
        ext([{"nome": "Amoxicilina", "dose": "500mg", "frequencia": "8/8h"}]),
        R.RECEITA_1,
    )
    assert e.medicamentos[0].frequencia == "8/8h" and p == []
    e, p, _ = validar(
        ext([{"nome": "Amoxicilina", "dose": "500mg", "frequencia": "6/6h"}]),
        R.RECEITA_1,
    )
    assert e.medicamentos[0].frequencia is None and p


def test_duracao_inventada_e_descartada():
    e, p, _ = validar(
        ext([{"nome": "Amoxicilina", "dose": "500mg", "duracao": "10 dias"}]),
        R.RECEITA_1,
    )
    assert e.medicamentos[0].duracao is None and p


# ---------------- nome e duplicatas ----------------
def test_medicamento_inventado_e_descartado_e_sinalizado():
    e, problemas, _ = validar(
        ext(
            [
                {"nome": "Amoxicilina", "dose": "500mg"},
                {"nome": "Morfina", "dose": "10mg"},
            ]
        ),
        R.RECEITA_1,
    )
    assert nomes(e) == ["Amoxicilina"] and any("Morfina" in p for p in problemas)


def test_nome_comercial_trocado_por_generico_e_sinalizado():
    texto = R.CABECALHO + "1) Amoxil 500mg, via oral."
    e, problemas, _ = validar(ext([{"nome": "Amoxicilina", "dose": "500mg"}]), texto)
    assert e.medicamentos == [] and any("Amoxicilina" in p for p in problemas)


def test_nome_com_palavra_a_mais_usa_a_primeira_palavra():
    texto = R.CABECALHO + "1) Dipirona 500mg, via oral."
    e, _, _ = validar(ext([{"nome": "Dipirona sódica", "dose": "500mg"}]), texto)
    assert len(e.medicamentos) == 1


def test_medicamento_repetido_vira_um_item_so():
    e, _, _ = validar(
        ext(
            [
                {"nome": "Amoxicilina", "dose": "500mg"},
                {"nome": "amoxicilina", "dose": "500 mg"},
            ]
        ),
        R.RECEITA_1,
    )
    assert len(e.medicamentos) == 1


def test_mesmo_medicamento_com_doses_diferentes_continua_separado():
    texto = R.CABECALHO + "1) Dipirona 500mg de manha. 2) Dipirona 1g a noite."
    e, _, _ = validar(
        ext(
            [{"nome": "Dipirona", "dose": "500mg"}, {"nome": "Dipirona", "dose": "1g"}]
        ),
        texto,
    )
    assert len(e.medicamentos) == 2


# ---------------- pela API e prompt ----------------
@pytest.fixture(autouse=True)
def _storage_local(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path / "storage"))
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)


def _enviar(extracao, texto, doc_id):
    client = TestClient(criar_app(lambda t: extracao))
    r = client.post(
        "/triagem?aguardar=true",
        json={
            "documento_id": doc_id,
            "tipo_arquivo": "TEXTO",
            "documento_texto": texto,
            "canal_origem": "Ambulatorio",
        },
    )
    assert r.status_code == 200
    return r.json()


def test_receita_de_rotina_leva_os_medicamentos_estruturados_ate_a_farmacia():
    j = _enviar(ext(R.ITENS_RECEITA_3), R.RECEITA_3, "REC-0003")
    assert j["decisao_roteamento"]["destino_principal"] == "Farmacia_Hospitalar"
    assert [m["nome"] for m in j["dados_extraidos"]["medicamentos"]] == [
        "Amoxicilina",
        "Dipirona",
        "Omeprazol",
    ]
    assert j["dados_extraidos"]["medicamentos"][0]["via"] == "via oral"


def test_receita_sem_dose_vai_para_revisao_com_o_motivo():
    j = _enviar(ext([{"nome": "Amoxicilina"}]), R.RECEITA_SEM_DOSE, "REC-SEM-DOSE")
    assert j["decisao_roteamento"]["destino_principal"] == "Fila_Revisao_Humana"
    assert any(p.startswith("campo faltante: dose") for p in j["problemas"])
    assert j["dados_extraidos"]["medicamentos"][0]["dose"] is None


def test_prompt_traz_as_regras_dos_medicamentos():
    p = PROMPT
    for trecho in (
        "CADA medicamento",
        "nunca agrupe",
        "não troque nome comercial",
        "Nunca deduza dose nem via",
    ):
        assert trecho in p
