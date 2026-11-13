"""H3.4.1 T3/T5 — componentes da página do caso."""

import pytest

from ui.componentes.caso import VAZIO, dados_do_caso
from ui.componentes.original import paginas_do_original


def test_dados_do_caso_completo():
    d = dados_do_caso(
        {
            "paciente": {"nome": "Maria Souza", "idade": 54},
            "origem": "Hospital X",
            "achado_principal": "Nódulo pulmonar 2,3 cm",
            "cid": "R91",
            "medico_solicitante": "Dr. João",
        }
    )
    assert d == {
        "paciente": "Maria Souza",
        "origem": "Hospital X",
        "achado": "Nódulo pulmonar 2,3 cm",
        "cid": "R91",
        "medico": "Dr. João",
    }


def test_dados_ausentes_viram_traco():
    d = dados_do_caso({"paciente": "Ana"})
    assert d["paciente"] == "Ana"
    assert d["cid"] == d["medico"] == d["origem"] == d["achado"] == VAZIO


def test_formato_real_da_api_com_dados_extraidos():
    d = dados_do_caso(
        {
            "status": "ok",
            "canal_origem": "email",
            "dados_extraidos": {
                "paciente": "Maria Souza",
                "medico_solicitante": "Dr. João",
                "diagnostico_principal": "Nódulo pulmonar",
                "cid": "não encontrado",
                "cid_sugerido": "R91",
            },
        }
    )
    assert d == {
        "paciente": "Maria Souza",
        "origem": "email",
        "achado": "Nódulo pulmonar",
        "cid": "R91",
        "medico": "Dr. João",
    }


def test_imagem_e_devolvida_como_esta():
    assert paginas_do_original(b"\x89PNG...", "image/png") == [b"\x89PNG..."]


def test_content_type_com_parametros_e_aceito():
    assert paginas_do_original(b"jpg", "image/jpeg; charset=binary") == [b"jpg"]


def test_tipo_nao_suportado_levanta_valueerror():
    with pytest.raises(ValueError):
        paginas_do_original(b"x", "application/zip")


def test_pdf_vira_uma_png_por_pagina():
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page().insert_text((72, 72), "teste")
    paginas = paginas_do_original(doc.tobytes(), "application/pdf")
    assert len(paginas) == 3
    assert all(p.startswith(b"\x89PNG") for p in paginas)


def test_pdf_respeita_max_paginas():
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for _ in range(5):
        doc.new_page()
    assert (
        len(paginas_do_original(doc.tobytes(), "application/pdf", max_paginas=2)) == 2
    )
