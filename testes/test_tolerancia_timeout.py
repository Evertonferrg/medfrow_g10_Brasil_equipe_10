"""Testes de tolerância a latência e redução de viagens ao OCI."""

from types import SimpleNamespace

from app import resposta, storage
from app.notificacao import ServicoNotificacao
from ui.services.http import timeout_api


def test_timeout_api_padrao_e_sobrescrita_por_env(monkeypatch):
    monkeypatch.delenv("API_TIMEOUT_CONEXAO_S", raising=False)
    monkeypatch.delenv("API_TIMEOUT_LEITURA_S", raising=False)
    assert timeout_api() == (5.0, 30.0)

    monkeypatch.setenv("API_TIMEOUT_CONEXAO_S", "8")
    monkeypatch.setenv("API_TIMEOUT_LEITURA_S", "45")
    assert timeout_api() == (8.0, 45.0)

    monkeypatch.setenv("API_TIMEOUT_CONEXAO_S", "invalido")
    monkeypatch.setenv("API_TIMEOUT_LEITURA_S", "-5")
    assert timeout_api() == (5.0, 30.0)


def test_carregar_resultado_tenta_pasta_preferencial_primeiro(monkeypatch):
    caminhos_tentados = []

    def fake_ler(caminho: str):
        caminhos_tentados.append(caminho)

    monkeypatch.setattr(storage, "ler", fake_ler)

    resultado = resposta.carregar_resultado(
        "DOC-REV-1", pasta_preferencial=resposta.PASTA_REVISAO
    )

    assert resultado is None
    assert caminhos_tentados[0] == "auditoria_humana/DOC-REV-1.json"
    assert len(caminhos_tentados) == len(resposta.PASTAS_RESULTADO)


def test_storage_existe_usa_head_object_no_oci(monkeypatch, tmp_path):
    monkeypatch.setenv("OCI_NAMESPACE", "ns-teste")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))

    chamadas = []

    class ClienteFalso:
        def head_object(self, ns, bucket, caminho):
            chamadas.append((ns, bucket, caminho))
            if caminho == "auditoria_humana/DOC-1.json":
                return SimpleNamespace(status=200)
            erro = RuntimeError("NotFound")
            erro.status = 404
            raise erro

        def get_object(self, *args, **kwargs):
            raise AssertionError("existe() não deve chamar get_object")

    monkeypatch.setattr(storage, "_cliente_oci", lambda: ClienteFalso())

    assert storage.existe("auditoria_humana/DOC-1.json") is True
    assert storage.existe("auditoria_humana/DOC-INEXISTENTE.json") is False
    assert len(chamadas) == 2


def test_notificacao_timeout_configuravel_por_env(monkeypatch):
    monkeypatch.delenv("NOTIFICACAO_TIMEOUT_S", raising=False)
    assert ServicoNotificacao()._timeout == 5.0

    monkeypatch.setenv("NOTIFICACAO_TIMEOUT_S", "15")
    assert ServicoNotificacao()._timeout == 15.0
