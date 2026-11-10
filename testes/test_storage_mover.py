import pytest

from app import storage


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)
    monkeypatch.setattr(storage.config, "pasta_local", lambda: str(tmp_path))
    monkeypatch.setattr(storage.config, "bucket", lambda: "bkt")
    return tmp_path


def test_mover_local_troca_de_prefixo_sem_deixar_copia(local):
    storage.salvar("auditoria_humana/D1.json", {"a": 1})
    storage.mover("auditoria_humana/D1.json", "processados/D1.json")
    assert not storage.existe("auditoria_humana/D1.json")
    assert storage.existe("processados/D1.json")


def test_mover_origem_inexistente_levanta_erro(local):
    with pytest.raises(FileNotFoundError):
        storage.mover("auditoria_humana/NAO.json", "processados/NAO.json")


def test_mover_recusa_caminho_inseguro(local):
    with pytest.raises(ValueError):
        storage.mover("../fora.json", "processados/x.json")


def test_mover_no_oci_usa_rename_object_e_nao_copia(monkeypatch):
    pytest.importorskip("oci")
    chamadas = []

    class ClienteFalso:  # sem put_object/copy_object: qualquer cópia dá AttributeError
        def rename_object(self, ns, bucket, detalhes):
            chamadas.append((ns, bucket, detalhes))

    monkeypatch.setenv("OCI_NAMESPACE", "ns-teste")
    monkeypatch.setattr(storage.config, "bucket", lambda: "bkt")
    monkeypatch.setattr(storage, "_cliente_oci", lambda: ClienteFalso())

    storage.mover("auditoria_humana/D2.json", "rejeitados/D2.json")

    assert len(chamadas) == 1
    ns, bucket, detalhes = chamadas[0]
    assert (ns, bucket) == ("ns-teste", "bkt")
    assert detalhes.source_name == "auditoria_humana/D2.json"
    assert detalhes.new_name == "rejeitados/D2.json"
