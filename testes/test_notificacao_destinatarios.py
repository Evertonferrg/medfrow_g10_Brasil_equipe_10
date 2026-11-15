from typing import ClassVar

import pytest

from app import notificacao

ServicoNotificacaoReal = notificacao.ServicoNotificacao


class ServicoNotificacaoFalso:
    """Simula o envio sem acessar Gmail ou Slack."""

    chamadas: ClassVar[list] = []

    def __init__(self, **kwargs):
        self.configuracao = kwargs
        self.__class__.chamadas.append(self)

    def enviar(self, documento_id, mensagem):
        self.documento_id = documento_id
        self.mensagem = mensagem
        return notificacao.ENVIADO


@pytest.fixture(autouse=True)
def preparar_teste(monkeypatch):
    ServicoNotificacaoFalso.chamadas = []

    monkeypatch.setattr(
        notificacao,
        "ServicoNotificacao",
        ServicoNotificacaoFalso,
    )

    monkeypatch.setattr(
        "app.destinatarios.buscar_responsaveis",
        lambda setor: [
            {
                "nome": f"Responsável {setor}",
                "tratamento": "Dr(a).",
                "funcao": setor,
                "email": f"{setor}@exemplo.com",
                "slack_id": "ID_SIMULADO",
            }
        ],
    )


def resultado(destino):
    return {
        "documento_id": "DOC-TESTE-001",
        "decisao_roteamento": {
            "destino_principal": destino,
            "notificacao_gerada": None,
        },
    }


@pytest.mark.parametrize(
    ("destino", "setor"),
    [
        ("Auditoria_Autorizacoes", "auditoria"),
        ("Farmacia_Hospitalar", "farmacia"),
    ],
)
def test_direciona_para_responsavel_do_setor(destino, setor):
    status = notificacao.notificar_responsavel_por_destino(resultado(destino))

    assert status == notificacao.ENVIADO
    assert len(ServicoNotificacaoFalso.chamadas) == 1

    servico = ServicoNotificacaoFalso.chamadas[0]

    assert servico.configuracao["email_destino"] == (f"{setor}@exemplo.com")
    assert servico.configuracao["funcao"] == setor
    assert servico.documento_id == "DOC-TESTE-001"


def test_notifica_todos_os_responsaveis(monkeypatch):
    responsaveis = [
        {
            "nome": "Responsável 1",
            "tratamento": "Dr(a).",
            "funcao": "auditoria",
            "email": "auditoria1@exemplo.com",
            "slack_id": "U111111",
        },
        {
            "nome": "Responsável 2",
            "tratamento": "Dr(a).",
            "funcao": "auditoria",
            "email": "auditoria2@exemplo.com",
            "slack_id": "U222222",
        },
    ]

    monkeypatch.setattr(
        "app.destinatarios.buscar_responsaveis",
        lambda setor: responsaveis,
    )

    status = notificacao.notificar_responsavel_por_destino(
        resultado("Auditoria_Autorizacoes")
    )

    assert status == notificacao.ENVIADO
    assert len(ServicoNotificacaoFalso.chamadas) == 2

    emails = [
        servico.configuracao["email_destino"]
        for servico in ServicoNotificacaoFalso.chamadas
    ]

    slack_ids = [
        servico.configuracao["slack_id"] for servico in ServicoNotificacaoFalso.chamadas
    ]

    assert emails == [
        "auditoria1@exemplo.com",
        "auditoria2@exemplo.com",
    ]

    assert slack_ids == [
        "U111111",
        "U222222",
    ]


def test_emergencia_direciona_para_plantao(monkeypatch):
    chamadas = []

    def alertar_falso(resultado, servico=None, **kwargs):
        chamadas.append(
            {
                "resultado": resultado,
                "servico": servico,
            }
        )
        return notificacao.ENVIADO

    monkeypatch.setattr(
        notificacao,
        "alertar_plantao",
        alertar_falso,
    )

    status = notificacao.notificar_responsavel_por_destino(
        resultado("Fila_Emergencia_Medica")
    )

    assert status == notificacao.ENVIADO
    assert len(chamadas) == 1

    assert chamadas[0]["resultado"]["documento_id"] == ("DOC-TESTE-001")

    assert chamadas[0]["servico"].configuracao["email_destino"] == (
        "plantao@exemplo.com"
    )
    assert chamadas[0]["servico"].configuracao["canal"] == "ambos"


@pytest.mark.parametrize(
    "destino",
    [
        "Fila_Revisao_Humana",
        "Prontuario_Eletronico",
        "Destino_Desconhecido",
    ],
)
def test_nao_notifica_destinos_sem_responsavel_automatico(destino):
    status = notificacao.notificar_responsavel_por_destino(resultado(destino))

    assert status is None
    assert ServicoNotificacaoFalso.chamadas == []


def test_documento_sem_id_retorna_falhou():
    documento = resultado("Auditoria_Autorizacoes")
    documento["documento_id"] = ""

    status = notificacao.notificar_responsavel_por_destino(documento)

    assert status == notificacao.FALHOU
    assert ServicoNotificacaoFalso.chamadas == []


def test_slack_api_envia_mensagem_direta_simulada(monkeypatch):
    monkeypatch.setenv(
        "SLACK_BOT_TOKEN",
        "xoxb-token-simulado",
    )

    chamadas = []

    class RespostaFalsa:
        def __init__(self, dados):
            self.dados = dados

        def raise_for_status(self):
            pass

        def json(self):
            return self.dados

    respostas = [
        RespostaFalsa(
            {
                "ok": True,
                "channel": {"id": "D123456"},
            }
        ),
        RespostaFalsa({"ok": True}),
    ]

    def post_falso(url, **kwargs):
        chamadas.append({"url": url, **kwargs})
        return respostas.pop(0)

    servico = ServicoNotificacaoReal(
        post=post_falso,
        slack_id="U123456",
    )

    servico._enviar_slack(
        documento_id="DOC-TESTE-001",
        mensagem="Mensagem simulada de teste.",
        link="",
    )

    assert len(chamadas) == 2

    assert chamadas[0]["url"].endswith("conversations.open")
    assert chamadas[0]["json"] == {"users": "U123456"}

    assert chamadas[1]["url"].endswith("chat.postMessage")
    assert chamadas[1]["json"]["channel"] == "D123456"

    assert "Mensagem simulada de teste." in (chamadas[1]["json"]["text"])

    assert chamadas[0]["headers"]["Authorization"] == ("Bearer xoxb-token-simulado")


def test_slack_api_retorna_erro_ao_abrir_conversa(monkeypatch):
    monkeypatch.setenv(
        "SLACK_BOT_TOKEN",
        "xoxb-token-simulado",
    )

    class RespostaFalsa:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "ok": False,
                "error": "user_not_found",
            }

    chamadas = []

    def post_falso(url, **kwargs):
        chamadas.append(url)
        return RespostaFalsa()

    servico = ServicoNotificacaoReal(
        post=post_falso,
        slack_id="U-INVALIDO",
    )

    with pytest.raises(RuntimeError, match="user_not_found"):
        servico._enviar_slack(
            documento_id="DOC-TESTE-002",
            mensagem="Teste de falha.",
            link="",
        )

    assert len(chamadas) == 1
    assert chamadas[0].endswith("conversations.open")
