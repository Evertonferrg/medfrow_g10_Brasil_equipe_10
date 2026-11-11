from pathlib import Path

import pytest

from app.manuscrito import LIMITE_MANUSCRITO, MOTIVO_REVISAO, processar_manuscrita
from app.schemas_manuscrito import ILEGIVEL, CampoLido, LeituraManuscrita, MedicamentoManuscrito

LIMITE = LIMITE_MANUSCRITO  # 0.9, definido em app/manuscrito.py
FIXTURES = Path(__file__).parent / "fixtures" / "manuscritas"


def _med(nome, s_nome, dose, s_dose):
    return MedicamentoManuscrito(
        nome=CampoLido(valor=nome, score=s_nome),
        dose=CampoLido(valor=dose, score=s_dose),
        frequencia=CampoLido(valor="8/8h", score=0.9),
    )


def _leitura(*meds):
    return LeituraManuscrita(paciente=CampoLido(valor="Maria Teste", score=0.9), medicamentos=list(meds))


def _fake(leitura):
    """FakeLLM: devolve a leitura pronta, sem chamar o Gemini."""
    return lambda imagens: leitura


def _imagem(nome):
    caminho = FIXTURES / nome
    if not caminho.exists():
        pytest.skip(f"fixture ausente: {nome}")
    return caminho.read_bytes()


# ---------- testes rápidos (FakeLLM, sem chamar o Gemini) ----------

def test_dose_com_score_baixo_vira_ilegivel_e_vai_para_revisao():
    chamadas = []
    leitura, status = processar_manuscrita(
        [b"img"], LIMITE, lambda d, m: chamadas.append((d, m)), "doc-1",
        ler=_fake(_leitura(_med("Amoxicilina", 0.95, "500 mg", 0.30))),  # LLM arriscou
    )
    assert leitura.medicamentos[0].dose.valor == ILEGIVEL
    assert leitura.medicamentos[0].dose.score == 0.0
    assert status == "revisao"
    assert chamadas == [("doc-1", MOTIVO_REVISAO)]


def test_nome_com_score_baixo_vira_ilegivel():
    leitura, status = processar_manuscrita(
        [b"img"], LIMITE, lambda *a: None, "doc-2",
        ler=_fake(_leitura(_med("Dipirona", 0.2, "1 g", 0.9))),
    )
    assert leitura.medicamentos[0].nome.valor == ILEGIVEL
    assert status == "revisao"


def test_receita_legivel_nao_vai_para_revisao():
    chamadas = []
    leitura, status = processar_manuscrita(
        [b"img"], LIMITE, lambda *a: chamadas.append(a), "doc-3",
        ler=_fake(_leitura(_med("Dipirona", 0.95, "1 g", 0.92))),
    )
    assert status == "ok" and chamadas == []
    assert leitura.medicamentos[0].dose.valor == "1 g"


def test_score_entre_070_e_090_vai_para_revisao():
    """Regressão: o Gemini deu 0.75 e 0.8 para trechos que chutou; com 0.7 passavam."""
    leitura, status = processar_manuscrita(
        [b"img"], LIMITE, lambda *a: None, "doc-7",
        ler=_fake(_leitura(_med("Rivotril", 0.75, "1 cp", 0.80))),
    )
    assert leitura.medicamentos[0].nome.valor == ILEGIVEL
    assert leitura.medicamentos[0].dose.valor == ILEGIVEL
    assert status == "revisao"


def test_ilegivel_declarado_pelo_llm_e_respeitado_mesmo_com_score_alto():
    leitura, status = processar_manuscrita(
        [b"img"], LIMITE, lambda *a: None, "doc-4",
        ler=_fake(_leitura(_med("Ilegível", 0.99, "10 mg", 0.95))),
    )
    assert leitura.medicamentos[0].nome.valor == ILEGIVEL
    assert status == "revisao"


def test_score_exatamente_no_limite_e_aceito():
    _, status = processar_manuscrita(
        [b"img"], LIMITE, lambda *a: None, "doc-5",
        ler=_fake(_leitura(_med("Dipirona", LIMITE, "1 g", LIMITE))),
    )
    assert status == "ok"


def test_dose_nao_escrita_nao_e_ilegivel():
    leitura, status = processar_manuscrita(
        [b"img"], LIMITE, lambda *a: None, "doc-6",
        ler=_fake(_leitura(_med("Dipirona", 0.95, None, 1.0))),
    )
    assert leitura.medicamentos[0].dose.valor is None
    assert status == "ok"


# ---------- testes reais (chamam o Gemini; rodar com -m llm) ----------

@pytest.mark.llm
def test_llm_real_dose_ilegivel_vai_para_revisao():
    leitura, status = processar_manuscrita(
        [_imagem("receita_dose_ilegivel.png")], LIMITE, lambda *a: None, "real"
    )
    assert status == "revisao"
    assert any(
        c.valor == ILEGIVEL for m in leitura.medicamentos for c in (m.nome, m.dose)
    )


@pytest.mark.llm
def test_llm_real_receita_pessima_vai_para_revisao():
    _, status = processar_manuscrita(
        [_imagem("receita_pessima.png")], LIMITE, lambda *a: None, "real"
    )
    assert status == "revisao"


@pytest.mark.llm
def test_llm_real_le_receita_legivel():
    leitura, status = processar_manuscrita(
        [_imagem("receita_legivel.jpg")], LIMITE, lambda *a: None, "real"
    )
    assert status == "ok"
    assert len(leitura.medicamentos) == 3

    meds = {(m.nome.valor or "").casefold(): m for m in leitura.medicamentos}
    paracetamol = next(m for n, m in meds.items() if "paracetamol" in n)
    amoxicilina = next(m for n, m in meds.items() if "amoxicilina" in n)
    dipirona = next(m for n, m in meds.items() if "dipirona" in n)

    assert "750" in (paracetamol.dose.valor or "")
    assert "500" in (amoxicilina.dose.valor or "")
    # a receita não traz concentração: o modelo não pode inventar "mg"
    assert "mg" not in (dipirona.dose.valor or "").casefold()