import io

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.api import criar_app

# from app.schemas import Exame, Extracao, Medicamento, Medico, Paciente
from app.schemas import Extracao, Medico, Paciente

LAUDO_TEP = (
    "HOSPITAL SANTA LUCIA - LAUDO DE EXAME RADIOLOFICO.Paciente: Carlos Eduardo Mendes, 52 anos. "
    "Solicitante: Dra. Renata Silveira CRM-SP 145892. Exame: Tomografia de Torax com contraste. "
    "Indicacao: Suspeita de embolia pulmonar aguda, dispneia subita. Achados: Falha de enchimento em "
    "arteria pulmonar principal direita compativel com TEP agudo. CONCLUSAO: Quadro compativel com "
    "Tromboembolismo Pulmonar Agudo. Sugere-se correlacao clinica urgente."
)
RECEITA = (
    "RECEITUARIO. Paciente: Maria Souza, 40 anos. Dr. Paulo Lima CRM 99887 SP. "
    "Amoxicilina 500mg de 8 em 8 horas por 7 dias."
)
GUIA = (
    "GUIA DE SOLICITACAO. Paciente: Joao Pereira, 61 anos. Dra. Ana Torres CRM-RJ 55443. "
    "Procedimento: Ressonancia de joelho codigo TUSS 40801020."
)


@pytest.fixture(autouse=True)
def storage_isolado(tmp_path, monkeypatch):
    """Cada teste grava numa pasta temporária e nunca usa a nuvem."""
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path / "storage"))
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)


def extracao(**kw) -> Extracao:
    base = {
        "tipo_documento": "Laudo de Exame de Imagem",
        "especialidade": "Radiologia / Pneumologia",
        "nivel_prioridade": "Urgente",
        "score_confianca_classificacao": 0.99,
        "paciente": Paciente(nome="Carlos Eduardo Mendes", idade=52),
        "medico_solicitante": Medico(nome="Dra. Renata Silveira", crm="CRM-SP 145892"),
        "diagnostico_principal": "Tromboembolismo Pulmonar Agudo (TEP)",
        "cid_sugerido": "I26.9",
    }
    base.update(kw)
    return Extracao(**base)


def extrator_fixo(ext):
    return lambda texto: ext


def extrator_que_quebra(texto):
    raise RuntimeError("Gemini fora do ar")


@pytest.fixture
def cliente():
    return TestClient(criar_app(extrator_fixo(extracao())))


def cliente_com(extrator):
    return TestClient(criar_app(extrator))


def pdf_com_texto(paginas: list) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for t in paginas:
        c.drawString(72, 750, t)
        c.showPage()
    c.save()
    return buf.getvalue()


def pdf_sem_texto() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(100, 100, 200, 200)  # só desenho, nenhum texto selecionável
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _eventos_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path / "eventos"))


@pytest.fixture(autouse=True)
def _sem_webhook_nos_testes(monkeypatch):
    """H3.3.2: nenhum teste chama o n8n de verdade, mesmo com N8N_WEBHOOK_URL no .env."""
    monkeypatch.delenv("N8N_WEBHOOK_URL", raising=False)
