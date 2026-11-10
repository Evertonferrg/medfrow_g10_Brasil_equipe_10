import pytest

from app import manutencao, storage


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)
    monkeypatch.setattr(storage.config, "pasta_local", lambda: str(tmp_path))
    monkeypatch.setattr(storage.config, "bucket", lambda: "bkt")


def test_id_em_um_prefixo_sai_com_0(local, capsys):
    storage.salvar("auditoria_humana/D1.json", {"a": 1})
    assert manutencao.main(["D1"]) == 0
    assert "auditoria_humana" in capsys.readouterr().out


def test_id_inexistente_sai_com_1(local, capsys):
    assert manutencao.main(["NAO-EXISTE"]) == 1
    assert "não encontrado" in capsys.readouterr().out


def test_id_em_dois_prefixos_sai_com_1(local):
    storage.salvar("auditoria_humana/D2.json", {"a": 1})
    storage.salvar("processados/rotina/D2.json", {"a": 1})
    assert manutencao.main(["D2"]) == 1


@pytest.mark.parametrize("args", [[], ["a", "b"], ["../x"], ["a/b"]])
def test_uso_incorreto_sai_com_2(args):
    assert manutencao.main(args) == 2
