"""H5.2.2 T5 — Testes da linha do tempo e histórico de um documento.

Cenários conforme critérios de aceite e tarefas:
  1. Padronização do modelo Evento (tipo, data_hora, autor, detalhe).
  2. Um documento de rotina tem os 5 eventos em ordem:
     recebimento, extração, classificação, decisão e destino.
  3. Duas gravações simultâneas não perdem evento (concorrência com concorrência otimista / thread safety).
  4. O serviço é append-only: não oferece método de editar ou apagar eventos.
  5. Rota GET /documentos/{documento_id}/historico devolve a lista de eventos em ordem cronológica.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.api import criar_app
from app.eventos import ServicoEventos
from app.modelos.evento import Evento
from app.schemas import Extracao, Medicamento, MedicoSolicitante, Paciente
from app.servico import processar
from app.status import StatusDocumento
from testes.conftest import extrator_fixo


# ---------------------------------------------------------------------------
# T1: Padronizar o modelo Evento
# ---------------------------------------------------------------------------
def test_t1_modelo_evento_padronizado():
    """T1: Evento com tipo, data_hora, autor e detalhe."""
    agora = datetime.now(timezone.utc).isoformat()
    ev = Evento(
        tipo="classificacao",
        data_hora=agora,
        autor="agente",
        detalhe="Laudo de Exame de Imagem (score 0.95)",
    )
    dados = ev.model_dump()
    assert dados["tipo"] == "classificacao"
    assert dados["data_hora"] == agora
    assert dados["autor"] == "agente"
    assert dados["detalhe"] == "Laudo de Exame de Imagem (score 0.95)"


# ---------------------------------------------------------------------------
# T2: Append-only e Concorrência Otimista
# ---------------------------------------------------------------------------
def test_t2_servico_nao_tem_metodos_de_editar_ou_apagar():
    """T2/T5: O ServicoEventos não expõe métodos para editar ou apagar eventos."""
    servico = ServicoEventos()
    assert not hasattr(servico, "editar")
    assert not hasattr(servico, "apagar")
    assert not hasattr(servico, "remover")
    assert not hasattr(servico, "deletar")
    assert not hasattr(servico, "atualizar")


def test_t2_t5_gravacoes_simultaneas_nao_perdem_eventos(tmp_path):
    """T2/T5: Gravações concorrentes em threads paralelas mantêm todos os eventos sem perdas."""
    servico = ServicoEventos(pasta=tmp_path)
    doc_id = "DOC-CONCORRENTE-01"

    num_threads = 10

    def gravar(i: int):
        servico.registrar(
            documento_id=doc_id,
            status=StatusDocumento.PROCESSANDO,
            tipo=f"passo_{i}",
            autor="agente",
            detalhe=f"execucao concorrente {i}",
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(gravar, range(num_threads)))

    eventos = servico.listar(doc_id)
    assert len(eventos) == num_threads
    # A cadeia de hashes de integridade deve estar íntegra
    assert servico.verificar_cadeia(doc_id) == []


# ---------------------------------------------------------------------------
# T1 e T5: Documento de rotina tem os 5 eventos em ordem
# ---------------------------------------------------------------------------
def test_t1_t5_documento_de_rotina_tem_eventos_em_ordem(tmp_path, monkeypatch):
    """Cenário principal: recebimento, extração, classificação, decisão e destino."""
    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path / "storage"))

    ext = Extracao(
        tipo_documento="Receituário Médico",
        especialidade="Clínica Geral",
        nivel_prioridade="Rotina",
        score_confianca_classificacao=0.95,
        paciente=Paciente(nome="Maria Souza", idade=40),
        medico_solicitante=MedicoSolicitante(nome="Dr. Paulo Lima", crm="CRM 99887 SP"),
        medicamentos=[Medicamento(nome="Amoxicilina", dose="500mg")],
    )

    texto = (
        "RECEITUARIO. Paciente: Maria Souza, 40 anos. Dr. Paulo Lima CRM 99887 SP. "
        "Amoxicilina 500mg de 8 em 8 horas por 7 dias."
    )

    client = TestClient(criar_app(extrator_fixo(ext)))

    # Envia via API para disparar o recebimento e o processamento completo
    resp = client.post(
        "/triagem",
        json={
            "documento_id": "DOC-ROTINA-HIST-1",
            "documento_texto": texto,
            "canal_origem": "Ambulatorio",
        },
    )
    assert resp.status_code == 202

    # Consulta o histórico
    servico = ServicoEventos(pasta=tmp_path)
    eventos = servico.listar_eventos("DOC-ROTINA-HIST-1")
    tipos = [e.tipo for e in eventos]

    # Verifica se os 5 eventos fundamentais ocorreram
    assert "recebido" in tipos or "recebimento" in tipos
    assert "extracao" in tipos
    assert "classificacao" in tipos
    assert "decisao" in tipos
    assert "destino" in tipos

    # Verifica ordem cronológica
    idx_rec = next(i for i, t in enumerate(tipos) if t in ("recebido", "recebimento"))
    idx_ext = tipos.index("extracao")
    idx_cla = tipos.index("classificacao")
    idx_dec = tipos.index("decisao")
    idx_des = tipos.index("destino")

    assert idx_rec < idx_ext < idx_cla < idx_dec < idx_des

    # Todos possuem data_hora válida
    for e in eventos:
        assert e.data_hora != ""
        assert e.autor != ""


# ---------------------------------------------------------------------------
# T3: Rota GET /documentos/{documento_id}/historico
# ---------------------------------------------------------------------------
def test_t3_get_historico_documento_api(tmp_path, monkeypatch):
    """T3: GET /documentos/{documento_id}/historico devolve 200 com lista de eventos."""
    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path))

    servico = ServicoEventos(pasta=tmp_path)
    servico.registrar("DOC-HIST-01", StatusDocumento.RECEBIDO, tipo="recebimento")
    servico.registrar("DOC-HIST-01", StatusDocumento.PROCESSANDO, tipo="extracao")
    servico.registrar("DOC-HIST-01", StatusDocumento.PROCESSADO, tipo="destino", detalhe="Prontuario_Eletronico")

    client = TestClient(criar_app())

    resp = client.get("/documentos/DOC-HIST-01/historico")
    assert resp.status_code == 200
    dados = resp.json()
    assert isinstance(dados, list)
    assert len(dados) == 3
    assert dados[0]["tipo"] in ("recebido", "recebimento")
    assert dados[1]["tipo"] == "extracao"
    assert dados[2]["tipo"] == "destino"


def test_t3_get_historico_documento_inexistente(tmp_path, monkeypatch):
    """GET /documentos/{documento_id}/historico com documento sem histórico devolve 404."""
    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path))
    client = TestClient(criar_app())
    resp = client.get("/documentos/DOC-NAO-EXISTE/historico")
    assert resp.status_code == 404
