import logging
import os
import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from urllib.parse import quote

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

DESTINOS_RESPONSAVEIS = {
    "Fila_Emergencia_Medica": "plantao",
    "Auditoria_Autorizacoes": "auditoria",
    "Farmacia_Hospitalar": "farmacia",
}


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
    """Envia alertas personalizados pelo Slack, Gmail ou pelos dois canais."""

    def __init__(
        self,
        canal: str | None = None,
        timeout: float = TIMEOUT_S,
        registrar_falha: Callable[[str, str], None] = _registrar_falha_padrao,
        post: Callable | None = None,
        smtp_factory: Callable | None = None,
        email_destino: str | None = None,
        nome_destinatario: str | None = None,
        tratamento: str | None = None,
        funcao: str | None = None,
        slack_id: str | None = None,
    ) -> None:
        self._canal = canal
        self._timeout = timeout
        self._registrar_falha = registrar_falha
        self._post = post
        self._smtp_factory = smtp_factory

        # Configurações de integração
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.slack_bot_token = os.getenv("SLACK_BOT_TOKEN", "").strip()
        self.slack_id = (slack_id or "").strip()
        self.gmail_user = os.getenv("GMAIL_USER")
        self.gmail_password = os.getenv("GMAIL_APP_PASSWORD")

        # Dados do destinatário
        self.email_destino = email_destino or os.getenv("PLANTAO_EMAIL_DESTINO")

        self.nome_destinatario = nome_destinatario or os.getenv(
            "NOTIFICACAO_NOME_DESTINATARIO",
            "Equipe responsável",
        )

        self.tratamento = tratamento or os.getenv(
            "NOTIFICACAO_TRATAMENTO",
            "",
        )

        self.funcao = funcao or os.getenv(
            "NOTIFICACAO_FUNCAO",
            "Equipe responsável",
        )

        # Mantém compatibilidade com o nome anterior do atributo.
        self.plantao_email_destino = self.email_destino

    def _nome_com_tratamento(self) -> str:
        """Monta a identificação personalizada do destinatário."""
        nome = self.nome_destinatario.strip()
        tratamento = self.tratamento.strip()

        if tratamento:
            return f"{tratamento} {nome}"

        return nome

    def _montar_mensagem(self, documento_id: str, motivo: str | None = None) -> str:
        """
        Monta uma mensagem operacional.

        Não inclui nome do paciente nem conteúdo extraído do documento.
        O motivo, quando informado, deve ser um texto genérico do roteamento.
        """
        destinatario = self._nome_com_tratamento()

        bloco_motivo = f"Motivo: {motivo}\n" if motivo else ""

        return (
            f"Olá, {destinatario}!\n\n"
            "O MediFlow identificou um documento que requer "
            "sua atenção prioritária.\n\n"
            f"Documento: {documento_id}\n"
            f"Setor responsável: {self.funcao}\n"
            f"{bloco_motivo}\n"
            "Por gentileza, acesse a plataforma MediFlow para "
            "consultar a solicitação e dar continuidade ao atendimento.\n\n"
            "Atenciosamente,\n"
            "Equipe MediFlow"
        )

    def _enviar_slack(
        self,
        documento_id: str,
        mensagem: str,
        link: str,
    ) -> None:
        """Envia a notificação por mensagem direta ou pelo webhook Slack."""
        payload_texto = f"*ALERTA MEDIFLOW*\n\n{mensagem}"

        if link:
            payload_texto += f"\n\n<{link}|Acessar plataforma MediFlow>"

        post = self._post or httpx.post

        # Envio individual por mensagem direta, quando há token e ID.
        if self.slack_bot_token and self.slack_id:
            headers = {
                "Authorization": f"Bearer {self.slack_bot_token}",
                "Content-Type": "application/json; charset=utf-8",
            }

            resposta = post(
                "https://slack.com/api/conversations.open",
                headers=headers,
                json={"users": self.slack_id},
                timeout=self._timeout,
            )
            resposta.raise_for_status()

            dados = resposta.json()
            if not dados.get("ok"):
                raise RuntimeError(
                    "Slack conversations.open: "
                    f"{dados.get('error', 'erro desconhecido')}"
                )

            canal_id = (dados.get("channel") or {}).get("id")
            if not canal_id:
                raise RuntimeError("Slack não retornou o ID da conversa.")

            resposta = post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={
                    "channel": canal_id,
                    "text": payload_texto,
                },
                timeout=self._timeout,
            )
            resposta.raise_for_status()

            dados = resposta.json()
            if not dados.get("ok"):
                raise RuntimeError(
                    f"Slack chat.postMessage: {dados.get('error', 'erro desconhecido')}"
                )

        else:
            # Mantém compatibilidade com o webhook central.
            if not self.slack_webhook_url:
                raise RuntimeError("Webhook Slack não configurado.")

            resposta = post(
                self.slack_webhook_url,
                json={"text": payload_texto},
                timeout=self._timeout,
            )
            resposta.raise_for_status()

        logger.info("Alerta enviado ao Slack. Documento: %s", documento_id)

    def _enviar_email(
        self,
        documento_id: str,
        mensagem: str,
        link: str,
    ) -> None:
        """Envia e-mail personalizado pelo Gmail."""
        msg = EmailMessage()

        msg["Subject"] = f"[AÇÃO PRIORITÁRIA] MediFlow - Documento {documento_id}"
        msg["From"] = self.gmail_user
        msg["To"] = self.email_destino

        corpo = mensagem

        if link:
            corpo += f"\n\nAcesse a plataforma MediFlow pelo endereço:\n{link}"

        corpo += "\n\n---\nSistema de Notificações Automáticas\nEquipe MediFlow"

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

        logger.info("E-mail enviado. Documento: %s", documento_id)

    def _registrar_erro(self, documento_id: str, erros: list[str]) -> None:
        """Registra uma única ocorrência de falha de notificação."""
        resumo = "; ".join(erros)[:200]

        try:
            self._registrar_falha(documento_id, resumo)
        except Exception:
            logger.exception(
                "Não foi possível registrar a falha de notificação (%s).",
                documento_id,
            )

    def enviar(self, documento_id: str, notificacao: dict | None) -> str:
        """Dispara a notificação pelos canais configurados."""
        canal = (self._canal or os.getenv("NOTIFICACAO_CANAL", "ambos")).strip().lower()

        if canal == "desativado":
            return DESATIVADO

        if canal not in ("slack", "email", "ambos"):
            logger.warning("Canal de notificação inválido: %s", canal)
            return DESATIVADO

        # O motivo vem do roteamento e deve ser um texto genérico,
        # sem dados do paciente
        motivo = (notificacao or {}).get("mensagem")
        mensagem = self._montar_mensagem(documento_id, motivo)

        base = os.getenv("UI_BASE_URL", "").rstrip("/")
        link = f"{base}/?doc={quote(str(documento_id), safe='')}" if base else ""

        canais = []

        if canal in ("slack", "ambos") and (
            self.slack_webhook_url or (self.slack_bot_token and self.slack_id)
        ):
            canais.append("slack")

        if (
            canal in ("email", "ambos")
            and self.gmail_user
            and self.gmail_password
            and self.email_destino
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
                elif nome_canal == "email":
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

    if not forcar and str(decisao.get("destino_principal")) != DESTINO_EMERGENCIA:
        return NAO_URGENTE

    documento_id = resultado.get("documento_id")

    if not documento_id:
        raise ValueError("Documento sem identificador para notificação.")

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


def notificar_responsavel_por_destino(resultado: dict) -> str | None:
    """
    Identifica o setor responsável e envia notificações
    individuais para todos os destinatários cadastrados.
    """
    from app.destinatarios import buscar_responsaveis

    decisao = resultado.get("decisao_roteamento") or {}

    destino = decisao.get("destino_principal")
    destino = getattr(destino, "value", destino)

    setor = DESTINOS_RESPONSAVEIS.get(str(destino))

    if setor is None:
        return None

    documento_id = resultado.get("documento_id")

    if not documento_id:
        logger.error("Documento sem identificador para notificação.")
        return FALHOU

    try:
        responsaveis = buscar_responsaveis(setor)
    except ValueError:
        logger.exception(
            "Configuração inválida de destinatários para o setor %s.",
            setor,
        )
        return FALHOU

    if not responsaveis:
        logger.error("Nenhum responsável cadastrado para o setor %s.", setor)
        return DESATIVADO

    resultados = []

    for responsavel in responsaveis:
        if not responsavel.get("email") and not responsavel.get("slack_id"):
            continue

        servico = ServicoNotificacao(
            email_destino=responsavel.get("email") or None,
            nome_destinatario=responsavel.get("nome") or "Equipe responsável",
            tratamento=responsavel.get("tratamento") or "",
            funcao=responsavel.get("funcao") or setor,
            slack_id=responsavel.get("slack_id") or None,
        )

        try:
            if setor == "plantao":
                status = alertar_plantao(resultado, servico=servico)
            else:
                status = servico.enviar(
                    documento_id,
                    decisao.get("notificacao_gerada"),
                )

        except Exception:
            logger.exception("Erro ao notificar destinatário do setor %s.", setor)
            status = FALHOU

        resultados.append(status)

        logger.info(
            "Notificação: documento=%s, setor=%s, destinatário=%s, status=%s",
            documento_id,
            setor,
            responsavel.get("nome", "não identificado"),
            status,
        )

    if not resultados:
        return DESATIVADO

    if FALHOU in resultados:
        return FALHOU

    if ENVIADO in resultados:
        return ENVIADO

    return DESATIVADO
