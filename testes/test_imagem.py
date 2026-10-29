import io
import os

import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.grafo import triar
from app.schemas import Extracao, Legibilidade


def _png(borrar: bool = False) -> bytes:
    img = Image.new("RGB", (600, 300), "white")
    ImageDraw.Draw(img).text((20, 20), "Paciente: Maria Teste\nHemograma normal", fill="black")
    if borrar:
        img = img.filter(ImageFilter.GaussianBlur(25))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _extracao_falsa():
    chamadas = []

    def extrator(texto):
        chamadas.append(texto)
        return Extracao(tipo_documento="Laudo Laboratorial", nivel_prioridade="Rotina",
                        score_confianca_classificacao=0.9)
    return extrator, chamadas


def test_imagem_legivel_chega_a_extrair_dados():
    extrator, chamadas = _extracao_falsa()
    leitor = lambda imagens: ("Paciente: Maria Teste. Hemograma normal.", Legibilidade(legivel=True))
    estado = triar("", extrator, pdf_bytes=_png(), leitor=leitor)
    assert chamadas == ["Paciente: Maria Teste. Hemograma normal."]
    assert estado["tipo_arquivo"] == "Imagem"


def test_imagem_borrada_vai_para_revisao_como_ilegivel():
    extrator, chamadas = _extracao_falsa()
    leitor = lambda imagens: ("", Legibilidade(legivel=False, motivo="imagem muito borrada"))
    estado = triar("", extrator, pdf_bytes=_png(borrar=True), leitor=leitor)
    assert chamadas == []                       # não passou por extrair_dados
    assert estado["requer_revisao"] is True
    assert estado["motivo_revisao"] == "ilegível"
    assert any("ilegível" in p for p in estado["problemas"])


def test_pdf_escaneado_e_convertido_em_png_por_pagina():
    import pymupdf
    doc = pymupdf.open()
    for _ in range(2):
        pagina = doc.new_page()
        pagina.insert_image(pagina.rect, stream=_png())
    pdf = doc.tobytes()

    recebidas = []

    def leitor(imagens):
        recebidas.extend(imagens)
        return "Hemograma normal, paciente Maria Teste.", Legibilidade(legivel=True)

    extrator, chamadas = _extracao_falsa()
    estado = triar("", extrator, pdf_bytes=pdf, leitor=leitor)
    assert len(recebidas) == 2 and all(i.startswith(b"\x89PNG") for i in recebidas)
    assert len(chamadas) == 1 and estado["tipo_arquivo"] == "PDF"


@pytest.mark.llm
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="sem GEMINI_API_KEY")
def test_completude_imagem_vs_pdf_digital():
    """Mesmo laudo em PDF digital e em imagem: a imagem não pode perder muita informação."""
    import pymupdf
    from app.llm import extrair, ler_imagem
    from app.pdf import extrair_texto_pdf

    laudo = ("Paciente: Maria Teste, 45 anos.\nMedico: Dr. Joao Souza CRM 12345 SP\n"
             "Hemograma completo: hemoglobina 14,2 g/dL, leucocitos 6.300/mm3.\n"
             "Diagnostico: sem alteracoes.")
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 80), laudo)
    pdf = doc.tobytes()
    png = doc[0].get_pixmap(dpi=150).tobytes("png")

    def completude(e):
        campos = [e.paciente.nome, e.paciente.idade, e.medico_solicitante.nome,
                  e.medico_solicitante.crm, e.diagnostico_principal]
        return sum(c is not None for c in campos)

    ref = completude(extrair(extrair_texto_pdf(pdf)))
    texto, leg = ler_imagem([png])
    assert leg.legivel
    assert completude(extrair(texto)) >= ref - 1