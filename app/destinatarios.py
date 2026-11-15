import os

from dotenv import load_dotenv

load_dotenv()


def _lista_env(nome: str) -> list[str]:
    """Carrega uma lista de valores separados por ponto e vírgula."""
    valor = os.getenv(nome, "")
    return [item.strip() for item in valor.split(";") if item.strip()]


def _carregar_responsavel(prefixo: str) -> dict:
    """Carrega os dados individuais de um responsável."""
    emails = _lista_env(f"{prefixo}_EMAILS")
    slack_ids = _lista_env(f"{prefixo}_SLACK_IDS")

    return {
        "nome": os.getenv(f"{prefixo}_NOME", "").strip(),
        "tratamento": os.getenv(f"{prefixo}_TRATAMENTO", "").strip(),
        "funcao": os.getenv(f"{prefixo}_FUNCAO", "").strip(),
        "email": emails[0] if emails else os.getenv(f"{prefixo}_EMAIL", "").strip(),
        "slack_id": slack_ids[0]
        if slack_ids
        else os.getenv(f"{prefixo}_SLACK_ID", "").strip(),
    }


RESPONSAVEIS = {
    "plantao": _carregar_responsavel("PLANTAO"),
    "auditoria": _carregar_responsavel("AUDITORIA"),
    "farmacia": _carregar_responsavel("FARMACIA"),
}


def buscar_responsavel(setor: str) -> dict | None:
    """Mantém compatibilidade: retorna o primeiro responsável."""
    return RESPONSAVEIS.get(setor)


def buscar_responsaveis(setor: str) -> list[dict]:
    """Retorna todos os destinatários cadastrados para um setor."""
    prefixos = {
        "plantao": "PLANTAO",
        "auditoria": "AUDITORIA",
        "farmacia": "FARMACIA",
    }

    prefixo = prefixos.get(setor)

    if prefixo is None:
        return []

    responsavel = RESPONSAVEIS[setor]

    emails = _lista_env(f"{prefixo}_EMAILS")
    slack_ids = _lista_env(f"{prefixo}_SLACK_IDS")

    if not emails and responsavel["email"]:
        emails = [responsavel["email"]]

    if not slack_ids and responsavel["slack_id"]:
        slack_ids = [responsavel["slack_id"]]

    if len(emails) != len(slack_ids) and emails and slack_ids:
        raise ValueError(
            f"Quantidade de e-mails e IDs Slack diferente no setor {setor}."
        )

    quantidade = max(len(emails), len(slack_ids))

    return [
        {
            **responsavel,
            "email": emails[i] if i < len(emails) else "",
            "slack_id": slack_ids[i] if i < len(slack_ids) else "",
        }
        for i in range(quantidade)
    ]
