"""H2.2.1 T5 — a justificativa cita tipo, prioridade e regra, tem no máximo 2 frases e bate com o destino."""

import io
import re

import pytest
from PIL import Image

from app import roteamento as rt
from app.grafo import triar
from app.schemas import Legibilidade
from testes.conftest import LAUDO_TEP, cliente_com, extracao, extrator_fixo


def frases(texto: str) -> list:
    """Conta frases sem quebrar em decimais como 0.95 (o ponto precisa ser seguido de espaço)."""
    return [f for f in re.split(r"(?<=[.!?])\s+", texto.strip()) if f]


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(buf, "PNG")
    return buf.getvalue()


CASOS_ROTEADOS = [
    ("Laudo de Exame de Imagem", "Urgente"),  # R-URGENCIA
    ("Receituário Médico", "Rotina"),  # R-RECEITA
    ("Guia de Solicitação de Procedimento", "Rotina"),  # R-GUIA
    ("Relatório de Alta", "Rotina"),  # R-PRONTUARIO
    ("Atestado Médico", "Rotina"),  # R-PRONTUARIO
]


@pytest.mark.parametrize("tipo,prioridade", CASOS_ROTEADOS)
def test_cada_regra_cita_tipo_prioridade_regra_e_destino(tipo, prioridade):
    decisao = rt.criar_decisao_roteamento(
        {
            "tipo_documento": tipo,
            "prioridade": prioridade,
            "score": 0.93,
            "problemas": [],
        }
    )

    texto = decisao.justificativa_roteamento
    assert tipo in texto
    assert prioridade in texto
    assert decisao.regra_aplicada in texto
    assert str(decisao.destino_principal) in texto


def test_toda_regra_tem_id_e_descricao_curta():
    for regra in ("R-URGENCIA", "R-REVISAO", "R-RECEITA", "R-GUIA", "R-PRONTUARIO"):
        assert rt.descricao_regra(regra)
    assert rt.descricao_regra("R-INEXISTENTE") == ""


# ---- critério 2: revisão diz qual dúvida levou o documento até lá ----
def test_revisao_lista_os_motivos_acumulados():
    texto = rt.gerar_justificativa(
        "",
        "",
        0.42,
        "Fila_Revisao_Humana",
        "R-REVISAO",
        problemas=["campo faltante: CRM", "inconsistência: idade x data de nascimento"],
    )
    assert "R-REVISAO" in texto and len(frases(texto)) <= 2


def test_revisao_sem_motivo_nem_problema_cita_a_baixa_confianca():
    texto = rt.gerar_justificativa("", "", 0.42, "Fila_Revisao_Humana", "R-REVISAO")
    assert "0.42" in texto


def test_revisao_por_erro_cita_a_falha():
    texto = rt.gerar_justificativa(
        "", "", 0.0, "Fila_Revisao_Humana", "R-REVISAO", erro="Gemini fora do ar"
    )
    assert "falha na extração automática" in texto and "Gemini fora do ar" in texto


def test_motivo_ilegivel_nao_se_repete():
    texto = rt.gerar_justificativa(
        "",
        "",
        0.0,
        "Fila_Revisao_Humana",
        "R-REVISAO",
        problemas=["ilegível: imagem borrada"],
    )
    assert "ilegível: imagem borrada" in texto and texto.count("ilegível") == 1


def test_imagem_ilegivel_chega_a_justificativa_do_grafo():
    leitor = lambda imagens: ("", Legibilidade(legivel=False, motivo="imagem borrada"))
    estado = triar(
        "", extrator_fixo(extracao()), _png(), leitor=leitor, documento_id="DOC-JUS-001"
    )
    assert (
        "ilegível" in estado["justificativa"]
        and "imagem borrada" in estado["justificativa"]
    )
    assert (
        estado["resultado"]["decisao_roteamento"]["justificativa_roteamento"]
        == estado["justificativa"]
    )


# ---- pela API: o destino citado bate com destino_principal ----
@pytest.mark.parametrize(
    "doc_id,kw",
    [
        # ("DOC-JUS-002", dict(nivel_prioridade="Urgente")),
        # ("DOC-JUS-003", dict(nivel_prioridade="Rotina")),
        ("DOC-JUS-002", {"nivel_prioridade": "Urgente"}),
        ("DOC-JUS-003", {"nivel_prioridade": "Rotina"}),
    ],
)
def test_destino_citado_bate_com_destino_principal(doc_id, kw):
    c = cliente_com(extrator_fixo(extracao(**kw)))
    corpo = {
        "documento_id": doc_id,
        "tipo_arquivo": "TEXTO",
        "documento_texto": LAUDO_TEP,
        "canal_origem": "Pronto_Socorro",
    }
    d = c.post("/triagem?aguardar=true", json=corpo).json()["decisao_roteamento"]
    texto = d["justificativa_roteamento"]
    assert len(frases(texto)) <= 2
    if d["requer_auditoria_humana"]:
        assert "revisão humana" in texto and "R-REVISAO" in texto
    else:
        assert d["destino_principal"] in texto and d["regra_aplicada"] in texto
