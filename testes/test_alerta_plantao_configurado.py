import pytest

from app import destinatarios, notificacao
from app.revisao import _alertar_plantao_configurado, colaboradores_padrao

RESPONSAVEL = {
    "nome": "Dra. Ana",
    "email": "ana@hospital.test",
    "tratamento": "Dra.",
    "funcao": "Médica de plantão",
}


def test_sem_responsavel_levanta_erro(monkeypatch):
    monkeypatch.setattr(destinatarios, "buscar_responsavel", lambda _: None)

    with pytest.raises(RuntimeError, match="não configurado"):
        _alertar_plantao_configurado({"documento_id": "doc-1"})


def test_responsavel_sem_email_levanta_erro(monkeypatch):
    monkeypatch.setattr(
        destinatarios, "buscar_responsavel", lambda _: {**RESPONSAVEL, "email": ""}
    )

    with pytest.raises(RuntimeError, match="não configurado"):
        _alertar_plantao_configurado({"documento_id": "doc-1"})


def test_configurado_envia_com_dados_do_responsavel(monkeypatch):
    capturado = {}

    monkeypatch.setattr(destinatarios, "buscar_responsavel", lambda papel: (
        capturado.setdefault("papel", papel) and RESPONSAVEL
    ))

    def falso_alertar(resultado, servico, levantar_em_falha):
        capturado["resultado"] = resultado
        capturado["servico"] = servico
        capturado["levantar_em_falha"] = levantar_em_falha
        return "enviado"

    monkeypatch.setattr(notificacao, "alertar_plantao", falso_alertar)

    resultado = {"documento_id": "doc-1"}
    _alertar_plantao_configurado(resultado)

    assert capturado["papel"] == "plantao"
    assert capturado["resultado"] is resultado
    assert capturado["levantar_em_falha"] is True
    assert capturado["servico"].email_destino == "ana@hospital.test"


def test_falha_no_envio_propaga(monkeypatch):
    monkeypatch.setattr(destinatarios, "buscar_responsavel", lambda _: RESPONSAVEL)

    def falha(*args, **kwargs):
        raise ConnectionError("SMTP fora do ar")

    monkeypatch.setattr(notificacao, "alertar_plantao", falha)

    with pytest.raises(ConnectionError):
        _alertar_plantao_configurado({"documento_id": "doc-1"})

def test_colaboradores_padrao_usa_alerta_configurado():
    assert colaboradores_padrao().alerta_plantao is _alertar_plantao_configurado