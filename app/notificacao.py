
import logging
import os
import smtplib
from collections.abc import Callable
from email.message import EmailMessage

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TIMEOUT_S = 5
ENVIADO = "enviado"
FALHOU = "falhou"
DESATIVADO = "desativado"
NAO_URGENTE = "nao_urgente"

DESTINO_EMERGENCIA = "Fila_Emergencia_Medica"


def _registrar_falha_padrao(documento_id: str, erro: str) -> None:
    """Registra falha de notificação sem alterar o status do documento."""
    from app.eventos import servico_padrao
    from app.status import StatusDocumento

    servico = servico_padrao()
    atual = servico.status_atual(documento_id) or StatusDocumento.PROCESSADO

    servico.registrar(
        documento_id,
        atual,
        detalhe="falha de notificação",
        tipo="notificacao",
    )


class ServicoNotificacao:
    """Envia alertas pelo Slack, Gmail ou pelos dois canais."""

    def __init__(
        self,
        canal: str | None = None,
        timeout: float = TIMEOUT_S,
        registrar_falha: Callable[[str, str], None] = _registrar_falha_padrao,
        post: Callable | None = None,
        smtp_factory: Callable | None = None,
    ) -> None:
        self._canal = canal
        self._timeout = timeout
        self._registrar_falha = registrar_falha
        self._post = post
        self._smtp_factory = smtp_factory

        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.gmail_user = os.getenv("GMAIL_USER")
        self.gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        self.plantao_email_destino = os.getenv("PLANTAO_EMAIL_DESTINO")

    def _enviar_slack(
        self,
        documento_id: str,
        mensagem: str,
        link: str,
    ) -> None:
        payload_texto = (
            f"🚨 *ALERTA MÉDICO - MediFlow* 🚨\n"
            f"*Documento:* `{documento_id}`\n"
            f"{mensagem}"
        )

        if link:
            payload_texto += f"\n🔗 <{link}|Ver na Interface>"

        post = self._post or httpx.post

        resposta = post(
            self.slack_webhook_url,
            json={"text": payload_texto},
            timeout=self._timeout,
        )
        resposta.raise_for_status()

        logger.info("Alerta enviado ao Slack (%s).", documento_id)

    def _enviar_email(
        self,
        documento_id: str,
        mensagem: str,
        link: str,
    ) -> None:
        msg = EmailMessage()
        msg["Subject"] = (
            f"[ALERTA MÉDICO URGENTE] MediFlow - Doc: {documento_id}"
        )
        msg["From"] = self.gmail_user
        msg["To"] = self.plantao_email_destino

        corpo = (
            "Prezado(a) plantonista,\n\n"
            f"{mensagem}\n\n"
            f"ID do Documento: {documento_id}"
        )

        if link:
            corpo += f"\nAcesse o caso na interface: {link}"

        corpo += "\n\n---\nSistema de Alertas Automáticos - MediFlow"
        msg.set_content(corpo)

        smtp_factory = self._smtp_factory or smtplib.SMTP

        with smtp_factory(
            "smtp.gmail.com",
            587,
            timeout=self._timeout,
        ) as servidor:
            servidor.starttls()
            servidor.login(self.gmail_user, self.gmail_password)
            servidor.send_message(msg)

        logger.info("E-mail enviado ao plantão (%s).", documento_id)

    def _registrar_erro(self, documento_id: str, erros: list[str]) -> None:
        """Registra uma única ocorrência, mesmo se os dois canais falharem."""
        resumo = "; ".join(erros)[:200]

        try:
            self._registrar_falha(documento_id, resumo)
        except Exception:
            logger.exception(
                "Não foi possível registrar a falha de notificação (%s).",
                documento_id,
            )

    def enviar(self, documento_id: str, notificacao: dict | None) -> str:
        canal = (
            self._canal
            or os.getenv("NOTIFICACAO_CANAL", "ambos")
        ).strip().lower()

        if canal == "desativado":
            return DESATIVADO

        if canal not in ("slack", "email", "ambos"):
            logger.warning("Canal de notificação inválido: %s", canal)
            return DESATIVADO

        mensagem = (notificacao or {}).get(
            "mensagem",
            f"Caso urgente na fila de emergência: {documento_id}",
        )

        base = os.getenv("UI_BASE_URL", "").rstrip("/")
        link = f"{base}/?doc={documento_id}" if base else ""

        canais = []

        if canal in ("slack", "ambos") and self.slack_webhook_url:
            canais.append("slack")

        if (
            canal in ("email", "ambos")
            and self.gmail_user
            and self.gmail_password
            and self.plantao_email_destino
        ):
            canais.append("email")

        if not canais:
            logger.warning(
                "Nenhum canal de notificação está configurado (%s).",
                documento_id,
            )
            return DESATIVADO

        erros = []

        for nome_canal in canais:
            try:
                if nome_canal == "slack":
                    self._enviar_slack(documento_id, mensagem, link)
                else:
                    self._enviar_email(documento_id, mensagem, link)

            except Exception as erro:
                logger.exception(
                    "Falha no envio pelo canal %s (%s).",
                    nome_canal,
                    documento_id,
                )
                erros.append(f"{nome_canal}: {erro}")

        if erros:
            self._registrar_erro(documento_id, erros)
            return FALHOU

        return ENVIADO


def alertar_plantao(
    resultado: dict,
    servico: ServicoNotificacao | None = None,
    levantar_em_falha: bool = False,
    forcar: bool = False,
) -> str:
    """Alerta o plantão somente para casos de emergência, salvo envio forçado."""

    decisao = resultado.get("decisao_roteamento") or {}

    if (
        not forcar
        and str(decisao.get("destino_principal")) != DESTINO_EMERGENCIA
    ):
        return NAO_URGENTE

    documento_id = resultado.get("documento_id")
    notificacao = decisao.get("notificacao_gerada")

    notificacao_servico = servico or ServicoNotificacao()
    status = notificacao_servico.enviar(documento_id, notificacao)

    if levantar_em_falha and status in (FALHOU, DESATIVADO):
        raise RuntimeError(f"plantão não alertado ({status})")

    return status


def alertar_plantao_revisao(resultado: dict) -> None:
    """Envia o alerta obrigatório após uma decisão de revisão para emergência."""

    alertar_plantao(
        resultado,
        levantar_em_falha=True,
        forcar=True,
    )
