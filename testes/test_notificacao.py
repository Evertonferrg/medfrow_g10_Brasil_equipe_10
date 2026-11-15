from email.message import EmailMessage

import pytest

from app.notificacao import (
    DESATIVADO,
    ENVIADO,
    FALHOU,
    NAO_URGENTE,
    ServicoNotificacao,
    _registrar_falha_padrao,
    alertar_plantao,
    alertar_plantao_revisao,
)

NOTIF = {
    "mensagem": "Suspeita de embolia pulmonar",
    "destino": "Fila_Emergencia_Medica",
}


def _resultado(destino, notificacao=None):
    return {
        "documento_id": "DOC-9",
        "decisao_roteamento": {
            "destino_principal": destino,
            "notificacao_gerada": notificacao,
        },
    }


class RespostaOk:
    def raise_for_status(self):
        pass


class RespostaErro:
    def raise_for_status(self):
        raise RuntimeError("HTTP 500")


class SMTPFake:
    def __init__(self, erro=None):
        self.erro = erro
        self.iniciou_tls = False
        self.login_realizado = False
        self.mensagem = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.iniciou_tls = True

    def login(self, usuario, senha):
        if self.erro == "login":
            raise RuntimeError("Falha de autenticação")
        self.login_realizado = True

    def send_message(self, mensagem):
        if self.erro == "envio":
            raise RuntimeError("Falha ao enviar e-mail")
        self.mensagem = mensagem


def _configurar_slack(monkeypatch):
    monkeypatch.setenv(
        "SLACK_WEBHOOK_URL",
        "https://slack.example/webhook",
    )


def _configurar_email(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "mediflow@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "senha-de-teste")
    monkeypatch.setenv(
        "PLANTAO_EMAIL_DESTINO",
        "plantao@example.com",
    )


def _servico_slack(monkeypatch, post, falhas=None):
    _configurar_slack(monkeypatch)

    return ServicoNotificacao(
        canal="slack",
        post=post,
        registrar_falha=lambda documento, erro: (
            falhas.append((documento, erro)) if falhas is not None else None
        ),
    )


# ---------- Slack ----------


def test_slack_envia_alerta_com_timeout_de_5_segundos(monkeypatch):
    chamadas = []

    def post(url, json, timeout):
        chamadas.append((url, json, timeout))
        return RespostaOk()

    servico = _servico_slack(monkeypatch, post)

    assert servico.enviar("DOC-1", NOTIF) == ENVIADO

    url, payload, timeout = chamadas[0]

    assert url == "https://slack.example/webhook"
    assert timeout == 5
    assert "DOC-1" in payload["text"]
    assert NOTIF["mensagem"] in payload["text"]


def test_slack_fora_do_ar_registra_falha_sem_levantar(monkeypatch):
    falhas = []

    def post(*args, **kwargs):
        raise RuntimeError("Conexão recusada")

    servico = _servico_slack(monkeypatch, post, falhas)

    assert servico.enviar("DOC-2", NOTIF) == FALHOU
    assert falhas[0][0] == "DOC-2"


def test_slack_http_500_registra_falha(monkeypatch):
    falhas = []

    servico = _servico_slack(
        monkeypatch,
        lambda *args, **kwargs: RespostaErro(),
        falhas,
    )

    assert servico.enviar("DOC-3", NOTIF) == FALHOU
    assert falhas[0][0] == "DOC-3"


def test_slack_sem_webhook_fica_desativado(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    falhas = []

    servico = ServicoNotificacao(
        canal="slack",
        registrar_falha=lambda d, e: falhas.append(d),
    )

    assert servico.enviar("DOC-4", NOTIF) == DESATIVADO
    assert falhas == []


# ---------- Gmail ----------


def test_gmail_envia_email_com_sucesso(monkeypatch):
    _configurar_email(monkeypatch)

    smtp = SMTPFake()
    chamadas = []

    def smtp_factory(host, porta, timeout):
        chamadas.append((host, porta, timeout))
        return smtp

    servico = ServicoNotificacao(
        canal="email",
        smtp_factory=smtp_factory,
    )

    assert servico.enviar("DOC-5", NOTIF) == ENVIADO

    assert chamadas == [("smtp.gmail.com", 587, 5)]
    assert smtp.iniciou_tls is True
    assert smtp.login_realizado is True
    assert isinstance(smtp.mensagem, EmailMessage)
    assert "DOC-5" in smtp.mensagem["Subject"]
    assert NOTIF["mensagem"] in smtp.mensagem.get_content()


def test_gmail_com_falha_registra_evento(monkeypatch):
    _configurar_email(monkeypatch)

    falhas = []
    smtp = SMTPFake(erro="envio")

    servico = ServicoNotificacao(
        canal="email",
        smtp_factory=lambda *args, **kwargs: smtp,
        registrar_falha=lambda d, e: falhas.append((d, e)),
    )

    assert servico.enviar("DOC-6", NOTIF) == FALHOU
    assert falhas[0][0] == "DOC-6"


def test_gmail_falha_de_autenticacao_registra_evento(monkeypatch):
    _configurar_email(monkeypatch)

    falhas = []
    smtp = SMTPFake(erro="login")

    servico = ServicoNotificacao(
        canal="email",
        smtp_factory=lambda *args, **kwargs: smtp,
        registrar_falha=lambda d, e: falhas.append((d, e)),
    )

    assert servico.enviar("DOC-15", NOTIF) == FALHOU
    assert falhas[0][0] == "DOC-15"
    assert smtp.login_realizado is False


def test_gmail_sem_credenciais_fica_desativado(monkeypatch):
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("PLANTAO_EMAIL_DESTINO", raising=False)

    servico = ServicoNotificacao(canal="email")

    assert servico.enviar("DOC-7", NOTIF) == DESATIVADO


# ---------- Slack e Gmail juntos ----------


def test_ambos_enviam_com_sucesso(monkeypatch):
    _configurar_slack(monkeypatch)
    _configurar_email(monkeypatch)

    chamadas_slack = []
    smtp = SMTPFake()

    def post(url, json, timeout):
        chamadas_slack.append(json)
        return RespostaOk()

    servico = ServicoNotificacao(
        canal="ambos",
        post=post,
        smtp_factory=lambda *args, **kwargs: smtp,
    )

    assert servico.enviar("DOC-8", NOTIF) == ENVIADO
    assert len(chamadas_slack) == 1
    assert smtp.mensagem is not None


def test_falha_slack_nao_impede_envio_gmail(monkeypatch):
    _configurar_slack(monkeypatch)
    _configurar_email(monkeypatch)

    falhas = []
    smtp = SMTPFake()

    def post(*args, **kwargs):
        raise RuntimeError("Slack indisponível")

    servico = ServicoNotificacao(
        canal="ambos",
        post=post,
        smtp_factory=lambda *args, **kwargs: smtp,
        registrar_falha=lambda d, e: falhas.append(d),
    )

    assert servico.enviar("DOC-9", NOTIF) == FALHOU
    assert smtp.mensagem is not None
    assert falhas == ["DOC-9"]


def test_falha_gmail_nao_impede_envio_slack(monkeypatch):
    _configurar_slack(monkeypatch)
    _configurar_email(monkeypatch)

    chamadas_slack = []
    falhas = []
    smtp = SMTPFake(erro="envio")

    def post(url, json, timeout):
        chamadas_slack.append(json)
        return RespostaOk()

    servico = ServicoNotificacao(
        canal="ambos",
        post=post,
        smtp_factory=lambda *args, **kwargs: smtp,
        registrar_falha=lambda d, e: falhas.append(d),
    )

    assert servico.enviar("DOC-10", NOTIF) == FALHOU
    assert len(chamadas_slack) == 1
    assert falhas == ["DOC-10"]


def test_ambos_sem_credenciais_fica_desativado(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("PLANTAO_EMAIL_DESTINO", raising=False)

    servico = ServicoNotificacao(canal="ambos")

    assert servico.enviar("DOC-11", NOTIF) == DESATIVADO


def test_canal_desativado_nao_tenta_enviar(monkeypatch):
    chamadas = []

    servico = ServicoNotificacao(
        canal="desativado",
        post=lambda *a, **k: chamadas.append(1),
    )

    assert servico.enviar("DOC-12", NOTIF) == DESATIVADO
    assert chamadas == []


# ---------- alertar_plantao ----------


def test_alertar_plantao_nao_envia_para_fila_nao_urgente():
    chamadas = []

    class ServicoFake:
        def enviar(self, documento_id, notificacao):
            chamadas.append(documento_id)
            return ENVIADO

    resultado = _resultado("Farmacia_Hospitalar")

    assert alertar_plantao(resultado, ServicoFake()) == NAO_URGENTE
    assert chamadas == []


def test_alertar_plantao_envia_para_emergencia():
    class ServicoFake:
        def enviar(self, documento_id, notificacao):
            assert documento_id == "DOC-9"
            assert notificacao == NOTIF
            return ENVIADO

    resultado = _resultado("Fila_Emergencia_Medica", NOTIF)

    assert alertar_plantao(resultado, ServicoFake()) == ENVIADO


def test_alertar_plantao_usa_mensagem_padrao_quando_nao_ha_notificacao():
    class ServicoFake:
        def enviar(self, documento_id, notificacao):
            assert documento_id == "DOC-9"
            assert notificacao is None
            return ENVIADO

    assert (
        alertar_plantao(
            _resultado("Fila_Emergencia_Medica"),
            ServicoFake(),
        )
        == ENVIADO
    )


def test_alertar_plantao_forcar_ignora_destino():
    chamadas = []

    class ServicoFake:
        def enviar(self, documento_id, notificacao):
            chamadas.append(documento_id)
            return ENVIADO

    resultado = _resultado("Fila_Revisao_Humana")

    assert (
        alertar_plantao(
            resultado,
            ServicoFake(),
            forcar=True,
        )
        == ENVIADO
    )

    assert chamadas == ["DOC-9"]


def test_alertar_plantao_levanta_quando_envio_falha():
    class ServicoFake:
        def enviar(self, documento_id, notificacao):
            return FALHOU

    with pytest.raises(RuntimeError):
        alertar_plantao(
            _resultado("Fila_Emergencia_Medica"),
            ServicoFake(),
            levantar_em_falha=True,
        )


def test_alertar_plantao_levanta_quando_nao_ha_canal_configurado():
    class ServicoFake:
        def enviar(self, documento_id, notificacao):
            return DESATIVADO

    with pytest.raises(RuntimeError):
        alertar_plantao(
            _resultado("Fila_Emergencia_Medica"),
            ServicoFake(),
            levantar_em_falha=True,
        )


# ---------- Revisão ----------


def test_alertar_plantao_revisao_forca_envio():
    chamadas = []

    class ServicoFake:
        def enviar(self, documento_id, notificacao):
            chamadas.append((documento_id, notificacao))
            return ENVIADO

    resultado = _resultado("Fila_Revisao_Humana", NOTIF)

    assert (
        alertar_plantao(
            resultado,
            servico=ServicoFake(),
            forcar=True,
            levantar_em_falha=True,
        )
        == ENVIADO
    )

    assert chamadas == [("DOC-9", NOTIF)]


def test_alertar_plantao_revisao_levanta_quando_envio_falha(monkeypatch):
    resultado = _resultado("Fila_Revisao_Humana", NOTIF)

    class ServicoFake:
        def enviar(self, documento_id, notificacao):
            return FALHOU

    # Impede qualquer envio real pelo Slack ou Gmail.
    monkeypatch.setattr(
        "app.notificacao.ServicoNotificacao",
        lambda: ServicoFake(),
    )

    with pytest.raises(RuntimeError):
        alertar_plantao_revisao(resultado)


# ---------- Trilha de auditoria ----------


def test_evento_de_falha_nao_muda_status_atual(tmp_path, monkeypatch):
    from app import eventos
    from app.status import StatusDocumento

    servico = eventos.ServicoEventos(tmp_path)
    servico.registrar("DOC-13", StatusDocumento.RECEBIDO)
    servico.registrar("DOC-13", StatusDocumento.PROCESSADO)

    monkeypatch.setattr(eventos, "servico_padrao", lambda: servico)

    _registrar_falha_padrao("DOC-13", "Falha de conexão")

    assert servico.status_atual("DOC-13") == StatusDocumento.PROCESSADO

    ultimo = servico.listar("DOC-13")[-1]

    assert ultimo["detalhe"] == "falha de notificação"
    assert ultimo["tipo"] == "notificacao"
    assert servico.verificar_cadeia("DOC-13") == []


def test_falha_ao_registrar_evento_nao_interrompe_envio(monkeypatch):
    _configurar_slack(monkeypatch)

    def post(*args, **kwargs):
        raise RuntimeError("Slack fora do ar")

    def registrar_falha(documento_id, erro):
        raise OSError("Disco cheio")

    servico = ServicoNotificacao(
        canal="slack",
        post=post,
        registrar_falha=registrar_falha,
    )

    assert servico.enviar("DOC-14", NOTIF) == FALHOU


def test_colaboradores_padrao_liga_alerta_do_plantao():
    from app.revisao import (
        _alertar_plantao_configurado,
        colaboradores_padrao,
    )

    assert colaboradores_padrao().alerta_plantao is _alertar_plantao_configurado
