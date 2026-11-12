import json
from datetime import datetime, timezone

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
        "DOC-1": datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc),
        "DOC-2": datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc),
    }
    novo = IndiceDocumentos()
    monkeypatch.setattr(indice_carga, "indice", novo)
    monkeypatch.setattr(storage, "listar", lambda p: [c for c in arquivos if c.startswith(p)])
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