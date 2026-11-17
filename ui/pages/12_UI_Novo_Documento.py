import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st
from services.estilo import PAGINA_DASHBOARD, PAGINA_LISTA, preparar_pagina

ARQUIVO_REGRAS = Path(__file__).resolve().parents[2] / "config" / "regras.json"
TIPO_ARQUIVO_TEXTO = "TEXTO"
TIPOS_ARQUIVO = ["pdf", "jpg", "jpeg", "png"]
MAX_TEXTO = 200_000
MAX_ARQUIVO = 10 * 1024 * 1024
TIMEOUT = (3.05, 15)
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}


def url_da_api() -> str:
    return os.getenv("API_URL", "http://localhost:8000").rstrip("/")


def url_valida(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.hostname)


def sem_https_fora_do_local(url: str) -> bool:
    p = urlparse(url)
    if p.scheme != "http":
        return False
    host = p.hostname or ""
    return host not in HOSTS_LOCAIS and "." in host


def carregar_canais() -> list[str]:
    try:
        dados = json.loads(ARQUIVO_REGRAS.read_text(encoding="utf-8"))
        return [str(c) for c in dados["canais_origem"]]
    except (OSError, KeyError, TypeError, ValueError):
        return []


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
    try:
        detalhe = resp.json().get("detail")
    except (ValueError, AttributeError):
        detalhe = None
    if isinstance(detalhe, str) and detalhe.strip():
        return detalhe.strip()[:300]
    return f"Erro no servidor (HTTP {resp.status_code}). Tente novamente em instantes."


def _resposta_envio(resp, documento_id: str) -> tuple[bool, str]:
    if resp.status_code == 202:
        try:
            corpo = resp.json()
        except ValueError:
            corpo = {}
        doc_id = corpo.get("documento_id") or documento_id
        status = corpo.get("status") or "recebido"
        return True, f"Documento **{doc_id}** recebido. Status: **{status}**."
    return False, mensagem_do_servidor(resp)


def enviar_documento(url_base: str, payload: dict) -> tuple[bool, str]:
    try:
        resp = requests.post(
            f"{url_base}/triagem", json=payload, timeout=TIMEOUT, allow_redirects=False
        )
    except requests.RequestException:
        return (
            False,
            "Não foi possível se comunicar com a API. Verifique se ela está no ar.",
        )
    return _resposta_envio(resp, payload["documento_id"])


def enviar_arquivo(
    url_base: str, documento_id: str, canal: str, arquivo
) -> tuple[bool, str]:
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
        return (
            False,
            "Não foi possível se comunicar com a API. Verifique se ela está no ar.",
        )
    return _resposta_envio(resp, documento_id)


def _enviar() -> None:
    ss = st.session_state
    n = ss.get("n_upload", 0)
    arquivo = ss.get(f"arquivo_{n}")
    texto = ss.get("texto_documento", "")
    doc_id = (ss.get("documento_id") or "").strip()

    if not doc_id:
        ss["_resultado"] = (False, "Informe o ID do documento.")
    elif arquivo is None and not texto.strip():
        ss["_resultado"] = (False, "documento vazio")
    elif arquivo is None and len(texto) > MAX_TEXTO:
        ss["_resultado"] = (False, f"documento acima de {MAX_TEXTO} caracteres")
    elif arquivo is not None and arquivo.size > MAX_ARQUIVO:
        ss["_resultado"] = (False, "arquivo acima de 10 MB")
    elif not ss.get("confirmo_sintetico"):
        ss["_resultado"] = (
            False,
            "Confirme que o documento contém apenas dados sintéticos.",
        )
    else:
        canal = ss.get("canal_origem", "")
        if arquivo is not None:  # arquivo tem prioridade sobre o texto
            ok, msg = enviar_arquivo(url_da_api(), doc_id, canal, arquivo)
        else:
            ok, msg = enviar_documento(
                url_da_api(), montar_payload(doc_id, texto, canal)
            )
        ss["_resultado"] = (ok, msg)
        if ok:
            ss["ultimo_documento_id"] = doc_id  # NOVO: para o Dashboard
            ss["texto_documento"] = ""
            ss["confirmo_sintetico"] = False
            ss["documento_id"] = novo_id()
            ss["n_upload"] = n + 1


# ------------------------------------------------------------------
# PÁGINA
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Novo documento · MediFlow", page_icon="🩺", layout="wide"
)
preparar_pagina()

st.page_link(PAGINA_LISTA, label="Voltar para Lista", icon=":material/arrow_back:")
st.title("Ingerir Novo Documento Clínico")

st.info(
    "🔒 Documentos clínicos contêm **dados pessoais sensíveis** de saúde (LGPD, art. 5º, II "
    "e art. 11). Nesta fase use apenas documentos **sintéticos**; não envie dados reais de pacientes."
)

URL = url_da_api()
if not url_valida(URL):
    st.error("A variável de ambiente API_URL é inválida. Use http:// ou https://.")
    st.stop()
if sem_https_fora_do_local(URL):
    st.warning(
        "A API não usa HTTPS: os dados trafegam sem criptografia. Não envie dados reais."
    )

canais = carregar_canais()
if not canais:
    st.error("Não consegui ler os canais de origem em config/regras.json.")
    st.stop()

if "documento_id" not in st.session_state:
    st.session_state["documento_id"] = novo_id()

resultado = st.session_state.pop("_resultado", None)
if resultado:
    (st.success if resultado[0] else st.error)(resultado[1])
    if resultado[0]:
        st.page_link(PAGINA_DASHBOARD, label="Ver no Dashboard", icon="🩺")

with st.container(key="card_cadastro"), st.form("envio", border=False):
    # Campos comuns aos dois modos
    c1, c2 = st.columns(2)
    with c1:
        st.text_input(
            "ID do documento",
            key="documento_id",
            max_chars=64,
            help="Identificador único. Letras, números, '_' ou '-'. "
            "Não use CPF, nome ou outro dado do paciente.",
        )
    with c2:
        st.selectbox(
            "Canal de origem",
            canais,
            key="canal_origem",
            help="De onde o documento chegou.",
        )

    aba_upload, aba_texto = st.tabs(["Upload", "Texto Direto"])

    with aba_upload:
        n_upload = st.session_state.get("n_upload", 0)
        arquivo = st.file_uploader(
            "Arraste o arquivo clínico aqui (PDF/Imagem)",
            type=TIPOS_ARQUIVO,
            key=f"arquivo_{n_upload}",
            max_upload_size=10,
        )
        if arquivo is not None:
            if (arquivo.type or "").startswith("image/"):
                st.image(arquivo, caption=arquivo.name, width=400)
            else:
                st.caption(f"📄 {arquivo.name} ({arquivo.size // 1024} KB)")

    with aba_texto:
        st.text_area(
            "Texto do documento",
            key="texto_documento",
            height=250,
            placeholder="Cole aqui o texto do laudo, receita, guia, alta ou atestado.",
        )

    st.checkbox(
        "Confirmo que este documento contém apenas dados sintéticos (sem dados reais de pacientes).",
        key="confirmo_sintetico",
    )
    st.form_submit_button("Enviar", type="primary", on_click=_enviar)
