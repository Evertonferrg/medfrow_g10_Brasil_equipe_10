"""Envio de documentos ao backend.

Sem dependência do Streamlit: as páginas chamam estas funções e cuidam só da tela.
"""

import json
import os
import uuid
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

import requests

ARQUIVO_REGRAS = Path(__file__).resolve().parents[2] / "config" / "regras.json"
TIPO_ARQUIVO_TEXTO = "TEXTO"
MAX_TEXTO = 200_000  # mesmo limite do servidor (app/schemas.py)
MAPA_EXTENSOES_UPLOADER = {"PDF": ["pdf"], "JPG": ["jpg", "jpeg"], "PNG": ["png"]}
TIMEOUT = (3.05, 15)  # (conexão, leitura) em segundos
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}


class ResultadoEnvio(NamedTuple):
    ok: bool
    mensagem: str
    ilegivel: bool = False
    motivo_ilegibilidade: str | None = None


# ------------------------------------------------------------------
# Configuração (config/regras.json)
# ------------------------------------------------------------------
def carregar_limites() -> tuple[int, list[str]]:
    """Tamanho máximo (MB) e formatos aceitos, de config/regras.json (H1.1.4 T1)."""
    try:
        dados = json.loads(ARQUIVO_REGRAS.read_text(encoding="utf-8"))
        max_mb = int(dados.get("tamanho_maximo_mb", 10))
        formatos = [
            str(f).upper() for f in dados.get("formatos_aceitos", ["PDF", "JPG", "PNG"])
        ]
        return max_mb, formatos
    except (OSError, KeyError, TypeError, ValueError):
        return 10, ["PDF", "JPG", "PNG"]


def extensoes_aceitas(formatos: list[str]) -> list[str]:
    """Converte os formatos (PDF, JPG...) nas extensões do st.file_uploader."""
    return [
        ext
        for fmt in formatos
        for ext in MAPA_EXTENSOES_UPLOADER.get(fmt, [fmt.lower()])
    ]


def carregar_canais() -> list[str]:
    """Opções do canal de origem, de config/regras.json."""
    try:
        dados = json.loads(ARQUIVO_REGRAS.read_text(encoding="utf-8"))
        return [str(c) for c in dados["canais_origem"]]
    except (OSError, KeyError, TypeError, ValueError):
        return []


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------
def url_da_api() -> str:
    """A URL da API vem de variável de ambiente (nunca fixa no código)."""
    return os.getenv("API_URL", "http://localhost:8000").rstrip("/")


def url_valida(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.hostname)


def sem_https_fora_do_local(url: str) -> bool:
    """True só quando o tráfego sai da rede local e vai sem criptografia.

    Considera local: localhost, 127.0.0.1, ::1 e qualquer host SEM ponto no nome,
    o que cobre nomes de container na rede interna (ex.: http://mediflow-app:8000).
    """
    p = urlparse(url)
    if p.scheme != "http":
        return False
    host = p.hostname or ""
    return host not in HOSTS_LOCAIS and "." in host


def novo_id() -> str:
    return f"DOC-{uuid.uuid4().hex[:8].upper()}"


def montar_payload(documento_id: str, texto: str, canal: str) -> dict:
    return {
        "documento_id": documento_id.strip(),
        "tipo_arquivo": TIPO_ARQUIVO_TEXTO,
        "documento_texto": texto,
        "canal_origem": canal,
    }


def mensagem_do_servidor(resp) -> str:
    """Mostra o 'detail' do servidor; se não houver, uma mensagem genérica."""
    try:
        detalhe = resp.json().get("detail")
    except (ValueError, AttributeError):
        detalhe = None
    if isinstance(detalhe, str) and detalhe.strip():
        return detalhe.strip()[:300]
    return f"Erro no servidor (HTTP {resp.status_code}). Tente novamente em instantes."


def _corpo_json(resp) -> dict:
    try:
        corpo = resp.json()
    except ValueError:
        return {}
    return corpo if isinstance(corpo, dict) else {}


def _resposta_envio(resp, documento_id: str) -> ResultadoEnvio:
    """Interpreta a resposta de /triagem e /triagem/arquivo (202 assíncrono ou 200 síncrono).

    H1.4.2 T3: se o resultado indicar ilegibilidade, devolve o motivo para a tela
    mostrar a instrução de nova foto.
    """
    if resp.status_code == 202:
        corpo = _corpo_json(resp)
        doc_id = corpo.get("documento_id") or documento_id
        status = corpo.get("status") or "recebido"
        return ResultadoEnvio(
            True, f"Documento **{doc_id}** recebido. Status: **{status}**."
        )

    if resp.status_code == 200:
        corpo = _corpo_json(resp)
        problemas = corpo.get("problemas")
        ilegivel = bool(corpo.get("ilegivel")) or (
            isinstance(problemas, list) and any("ilegível" in str(p) for p in problemas)
        )
        doc_id = corpo.get("documento_id") or documento_id
        return ResultadoEnvio(
            True,
            f"Documento **{doc_id}** processado.",
            ilegivel=ilegivel,
            motivo_ilegibilidade=corpo.get("motivo_ilegibilidade"),
        )

    return ResultadoEnvio(False, mensagem_do_servidor(resp))


_ERRO_CONEXAO = "Não foi possível se comunicar com a API. Verifique se ela está no ar."


def enviar_documento(url_base: str, payload: dict) -> ResultadoEnvio:
    try:
        resp = requests.post(
            f"{url_base}/triagem", json=payload, timeout=TIMEOUT, allow_redirects=False
        )
    except requests.RequestException:
        # Sem str(e): a exceção pode trazer URL e detalhes internos.
        return ResultadoEnvio(False, _ERRO_CONEXAO)
    return _resposta_envio(resp, payload["documento_id"])


def enviar_arquivo(url_base: str, documento_id: str, canal: str, arquivo) -> ResultadoEnvio:
    """H1.1.3 T6: envia PDF, JPG ou PNG para POST /triagem/arquivo."""
    try:
        resp = requests.post(
            f"{url_base}/triagem/arquivo",
            data={"documento_id": documento_id.strip(), "canal_origem": canal},
            files={
                "arquivo": (
                    arquivo.name,
                    arquivo.getvalue(),
                    arquivo.type or "application/octet-stream",
                )
            },
            timeout=TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        return ResultadoEnvio(False, _ERRO_CONEXAO)
    return _resposta_envio(resp, documento_id)


def validar_envio(
    documento_id: str, texto: str, arquivo, confirmou: bool, tamanho_maximo_mb: int
) -> str | None:
    """Devolve a mensagem de erro, ou None se o envio pode seguir."""
    if not documento_id.strip():
        return "Informe o ID do documento."
    if arquivo is None and not texto.strip():
        return "Documento vazio: anexe um arquivo, tire uma foto ou digite um texto."
    if arquivo is None and len(texto) > MAX_TEXTO:
        return f"Documento acima de {MAX_TEXTO} caracteres."
    if arquivo is not None and arquivo.size > tamanho_maximo_mb * 1024 * 1024:
        return f"Arquivo acima do limite de {tamanho_maximo_mb} MB."
    if not confirmou:
        return "Confirme que o documento contém apenas dados sintéticos (LGPD)."
    return None


def enviar(
    url_base: str, documento_id: str, canal: str, texto: str, arquivo=None
) -> ResultadoEnvio:
    """Arquivo (ou foto) tem prioridade sobre o texto."""
    if arquivo is not None:
        return enviar_arquivo(url_base, documento_id, canal, arquivo)
    return enviar_documento(url_base, montar_payload(documento_id, texto, canal))