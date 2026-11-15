
import pytest

from app import notificacao, servico


def executar_processamento(monkeypatch, destino, notificacao_ativa=True):
    resultado = {
        "documento_id": "DOC-TESTE-001",
        "decisao_roteamento": {
            "destino_principal": destino,
            "notificacao_gerada": None,
        },
    }

    chamadas = []

    monkeypatch.setattr(
        servico,
        "triar",
        lambda *args, **kwargs: {},
    )

    monkeypatch.setattr(
        servico,
        "arquivar",
        lambda documento_id, estado: resultado,
    )

    monkeypatch.setattr(
        servico,
        "registrar_resultado",
        lambda documento_id, resultado: None,
    )

    monkeypatch.setenv(
        "NOTIFICACAO_AUTOMATICA",
        "true" if notificacao_ativa else "false",
    )

    monkeypatch.setattr(
        notificacao,
        "notificar_responsavel_por_destino",
        lambda resultado: chamadas.append(resultado)
        or notificacao.ENVIADO,
    )

    servico.processar(
        documento_id="DOC-TESTE-001",
        texto="Documento de teste",
        pdf_bytes=None,
        extrator=None,
    )

    return chamadas


def test_emergencia_dispara_notificacao_automatica(monkeypatch):
    chamadas = executar_processamento(
        monkeypatch,
        "Fila_Emergencia_Medica",
    )

    assert len(chamadas) == 1
    assert chamadas[0]["documento_id"] == "DOC-TESTE-001"


@pytest.mark.parametrize(
    "destino",
    [
        "Auditoria_Autorizacoes",
        "Farmacia_Hospitalar",
        "Fila_Revisao_Humana",
    ],
)
def test_outros_destinos_nao_disparam_alerta(monkeypatch, destino):
    chamadas = executar_processamento(monkeypatch, destino)

    assert chamadas == []


def test_notificacao_desativada_nao_dispara_alerta(monkeypatch):
    chamadas = executar_processamento(
        monkeypatch,
        "Fila_Emergencia_Medica",
        notificacao_ativa=False,
    )

    assert chamadas == []
