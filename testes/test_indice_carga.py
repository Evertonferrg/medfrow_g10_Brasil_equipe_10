import json
from datetime import UTC, datetime

from app import indice_carga, storage
from app.indice_documentos import IndiceDocumentos


def _resultado(doc_id, tipo="Laudo Laboratorial"):
    return {
        "documento_id": doc_id,
        "classificacao": {"tipo_documento": tipo, "nivel_prioridade": "Rotina"},
        "decisao_roteamento": {"destino_principal": "Fila_Laboratorio"},
    }


def test_reconstruir_ignora_json_corrompido_e_ordena_pela_chegada(monkeypatch):
    arquivos = {
        "processados/DOC-1.json": json.dumps(_resultado("DOC-1")).encode(),
        "processados/DOC-2.json": json.dumps(_resultado("DOC-2")).encode(),
        "rejeitados/DOC-3.json": b"{corrompido",
    }
    chegadas = {
        "DOC-1": datetime(2026, 11, 12, 8, 0, tzinfo=UTC),
        "DOC-2": datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
    }
    novo = IndiceDocumentos()
    monkeypatch.setattr(indice_carga, "indice", novo)
    monkeypatch.setattr(
        storage, "listar", lambda p: [c for c in arquivos if c.startswith(p)]
    )
    monkeypatch.setattr(storage, "ler", lambda c: arquivos.get(c))
    monkeypatch.setattr(indice_carga, "_chegada", lambda d: chegadas.get(d))
    monkeypatch.setattr(indice_carga, "_status", lambda d, r: "Processado")

    assert indice_carga.reconstruir_do_bucket() == 2
    assert [r.documento_id for r in novo.listar()] == ["DOC-2", "DOC-1"]


def test_resultado_preserva_canal_e_data_da_chegada(monkeypatch):
    novo = IndiceDocumentos()
    monkeypatch.setattr(indice_carga, "indice", novo)
    monkeypatch.setattr(indice_carga, "_status", lambda d, r: "Processado")

    indice_carga.registrar_chegada("DOC-1", "Laboratorio")
    chegada = novo.obter("DOC-1")
    assert chegada.status and chegada.canal_origem == "Laboratorio"

    indice_carga.registrar_resultado("DOC-1", _resultado("DOC-1"))
    final = novo.listar("Laboratorio")[0]
    assert final.status == "Processado"
    assert final.destino == "Fila_Laboratorio"
    assert final.data == chegada.data


def test_falha_no_indice_nao_quebra_o_processamento(monkeypatch):
    class Quebrado:
        def obter(self, _):
            raise RuntimeError("falha de teste")

    monkeypatch.setattr(indice_carga, "indice", Quebrado())
    indice_carga.registrar_resultado("DOC-1", _resultado("DOC-1"))  # não levanta


def test_reconstruir_ignora_estado_json_sem_aviso(monkeypatch, caplog):
    arquivos = {
        "auditoria_humana/DOC-1.json": json.dumps(_resultado("DOC-1")).encode(),
        "auditoria_humana/DOC-1.estado.json": json.dumps({"extracao": {}}).encode(),
    }
    novo = IndiceDocumentos()
    monkeypatch.setattr(indice_carga, "indice", novo)
    monkeypatch.setattr(
        storage, "listar", lambda p: [c for c in arquivos if c.startswith(p)]
    )
    monkeypatch.setattr(storage, "ler", lambda c: arquivos.get(c))
    monkeypatch.setattr(indice_carga, "_chegada", lambda d: None)
    monkeypatch.setattr(indice_carga, "_status", lambda d, r: "em_auditoria_humana")

    with caplog.at_level("WARNING"):
        assert indice_carga.reconstruir_do_bucket() == 1

    assert not any(".estado.json" in rec.message for rec in caplog.records)
    assert [r.documento_id for r in novo.listar()] == ["DOC-1"]


def test_indice_revisao_inclui_caso_legado_sem_eventos(tmp_path):
    from app.eventos import ServicoEventos
    from app.indice_documentos import ResumoDocumento
    from app.indice_revisao import IndiceRevisao

    ev = ServicoEventos(tmp_path)
    idx_docs = IndiceDocumentos()
    idx_docs.atualizar(
        ResumoDocumento(
            documento_id="DOC-LEGADO",
            tipo_documento="Laudo de Exame de Imagem",
            nivel_prioridade="Urgente",
            destino="Fila_Revisao_Humana",
            status="em_auditoria_humana",
            data=datetime(1970, 1, 1, tzinfo=UTC),
        )
    )
    resultado_legado = {
        "documento_id": "DOC-LEGADO",
        "classificacao": {
            "tipo_documento": "Laudo de Exame de Imagem",
            "nivel_prioridade": "Urgente",
        },
        "problemas": ["score global abaixo do limite (0.60 < 0.80)"],
    }

    idx_rev = IndiceRevisao(
        ev,
        carregar=lambda d: resultado_legado if d == "DOC-LEGADO" else None,
        indice_documentos=idx_docs,
    )
    casos = idx_rev.listar_casos_revisao()
    assert len(casos) == 1
    assert casos[0].documento_id == "DOC-LEGADO"
    assert casos[0].prioridade == "Urgente"
