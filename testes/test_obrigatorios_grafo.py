import io

from PIL import Image, ImageFilter

from app.grafo import triar
from app.schemas import (
    Exame,
    Extracao,
    Legibilidade,
    Medicamento,
    MedicoSolicitante,
    Paciente,
)

TEXTO_RECEITA = "Receituario. Dr. Paulo Lima CRM 99887 SP. Dipirona. Tomar se dor."
TEXTO_GUIA = (
    "Guia de solicitacao. Paciente: Joao Pereira. Dra. Ana Torres CRM RJ 55443."
)


def _receita(paciente_nome=None, dose=None):
    return Extracao(
        tipo_documento="Receituário Médico",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.95,
        paciente=Paciente(nome=paciente_nome),
        medico_solicitante=MedicoSolicitante(nome="Dr. Paulo Lima", crm="CRM 99887 SP"),
        medicamentos=[Medicamento(nome="Dipirona", dose=dose)],
    )


def _guia(exames):
    return Extracao(
        tipo_documento="Guia de Solicitação de Procedimento",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.95,
        paciente=Paciente(nome="Joao Pereira"),
        medico_solicitante=MedicoSolicitante(
            nome="Dra. Ana Torres", crm="CRM-RJ 55443"
        ),
        exames=exames,
    )


def test_receita_sem_paciente_e_dose_vai_para_revisao_com_as_duas_faltas():
    s = triar(TEXTO_RECEITA, lambda _t: _receita())
    r = s["resultado"]
    assert r["decisao_roteamento"]["destino_principal"] == "Fila_Revisao_Humana"
    assert r["decisao_roteamento"]["requer_auditoria_humana"] is True
    assert "campo faltante: nome_paciente" in r["problemas"]
    assert "campo faltante: dose" in r["problemas"]


def test_guia_sem_procedimento_vai_para_revisao_com_a_falta():
    s = triar(TEXTO_GUIA, lambda _t: _guia([]))
    r = s["resultado"]
    assert r["decisao_roteamento"]["destino_principal"] == "Fila_Revisao_Humana"
    assert "campo faltante: procedimento" in r["problemas"]


def test_guia_completa_nao_gera_campo_faltante():
    texto = TEXTO_GUIA + " Exame: Ressonancia de joelho."
    s = triar(texto, lambda _t: _guia([Exame(nome="Ressonancia de joelho")]))
    problemas = s["resultado"]["problemas"]
    assert not [p for p in problemas if p.startswith("campo faltante")]


def test_receita_completa_nao_gera_campo_faltante():
    texto = (
        "Receituario. Paciente: Maria Souza. Dr. Paulo Lima CRM 99887 SP. "
        "Dipirona 500mg."
    )
    s = triar(texto, lambda _t: _receita("Maria Souza", "500mg"))
    problemas = s["resultado"]["problemas"]
    assert not [p for p in problemas if p.startswith("campo faltante")]


def _png(modo):
    img = Image.new("RGB", (400, 300), "white")
    if modo == "borrada":
        img = img.filter(ImageFilter.GaussianBlur(25))
    elif modo == "baixa_resolucao":
        img = img.resize((8, 6))
    elif modo == "cortada":
        img = img.crop((0, 0, 400, 20))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_imagens_ilegiveis_terminam_em_revisao_sem_campo_preenchido():
    def leitor(_imagens):
        return "", Legibilidade(legivel=False, motivo="imagem ilegível")

    for modo in ("borrada", "baixa_resolucao", "cortada"):
        s = triar("", pdf_bytes=_png(modo), leitor=leitor, documento_id="DOC-ILEG-1")
        r = s["resultado"]
        assert r["decisao_roteamento"]["destino_principal"] == "Fila_Revisao_Humana"
        assert any("ilegível" in p for p in r["problemas"])
        assert r["dados_extraidos"]
        assert all(v == "não encontrado" for v in r["dados_extraidos"].values())
