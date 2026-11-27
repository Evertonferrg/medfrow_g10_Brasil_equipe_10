import sys
from pathlib import Path

import streamlit as st

# Garante que as importações da pasta ui funcionem em qualquer ambiente
PASTA_UI = str(Path(__file__).resolve().parents[1])
if PASTA_UI not in sys.path:
    sys.path.insert(0, PASTA_UI)

from services import envio
from services.estilo import PAGINA_LISTA, preparar_pagina
from services.navegacao import abrir_caso, definir_caso

TAMANHO_MAXIMO_MB, FORMATOS_ACEITOS = envio.carregar_limites()
TIPOS_ARQUIVO = envio.extensoes_aceitas(FORMATOS_ACEITOS)

# H1.4.2 T3: instruções por motivo de ilegibilidade
MENSAGEM_ILEGIBILIDADE = {
    "inclinacao": "📐 **Foto inclinada.** Tire uma nova foto alinhando o documento com a câmera.",
    "sombra": (
        "🌑 **Sombra detectada.** Tire a foto em ambiente com boa iluminação, "
        "evitando luz atrás do documento."
    ),
    "corte": (
        "✂️ **Documento cortado.** Inclua o documento inteiro na foto, "
        "garantindo que todas as bordas apareçam."
    ),
}
MENSAGEM_ILEGIBILIDADE_PADRAO = (
    "🔍 **Documento ilegível.** Verifique se o arquivo está nítido e tente novamente."
)


def _enviar() -> None:
    """Roda ao clicar em 'Enviar para Triagem', antes da página ser redesenhada."""
    ss = st.session_state
    n = ss.get("nd_n", 0)
    arquivo = ss.get(f"nd_arquivo_{n}")
    if arquivo is None:  # H1.4.2 T5: a foto da câmera vale quando não há arquivo
        arquivo = ss.get(f"nd_camera_{n}")
    texto = (ss.get("nd_texto") or "").strip()
    doc_id = (ss.get("nd_documento_id") or "").strip()

    erro = envio.validar_envio(
        doc_id, texto, arquivo, bool(ss.get("nd_confirmo")), TAMANHO_MAXIMO_MB
    )
    if erro:
        ss["nd_resultado"] = (False, erro)
        return

    res = envio.enviar(
        envio.url_da_api(), doc_id, ss.get("nd_canal", ""), texto, arquivo
    )
    ss["nd_resultado"] = (res.ok, res.mensagem)
    ss.pop("nd_aviso", None)
    if res.ok:
        if res.ilegivel:
            ss["nd_aviso"] = res.motivo_ilegibilidade or ""  # "" = motivo não informado
        definir_caso(doc_id)  # o Dashboard lê este ID
        ss["nd_doc_enviado"] = doc_id  # guarda para o botão do Dashboard
        ss["nd_texto"] = ""  # não deixa conteúdo clínico parado na sessão
        ss["nd_confirmo"] = False
        ss["nd_documento_id"] = envio.novo_id()
        ss["nd_n"] = n + 1  # novas chaves = uploader e câmera limpos


# ------------------------------------------------------------------
# PÁGINA
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Novo Documento · MediFlow", page_icon="🩺", layout="wide"
)
preparar_pagina()

# ------------------------------------------------------------------
# BARRA SUPERIOR (Padrão MediFlow: Voltar à esquerda e Dashboard à direita)
# ------------------------------------------------------------------
doc_enviado = st.session_state.get("nd_doc_enviado")

c_voltar, _, c_dash = st.columns([3, 4.5, 2.5], vertical_alignment="center")
with c_voltar, st.container(key="btn_voltar"):
    st.page_link(
        st.Page(f"{PASTA_UI}/{PAGINA_LISTA}"),
        label="Voltar para Lista Documentos",
        icon=":material/arrow_back:",
    )

if doc_enviado:
    with c_dash:
        if st.button(
            "Ver caso no Dashboard",
            key="nd_ver_dashboard",
            type="primary",
            icon=":material/open_in_new:",
            width="stretch",
        ):
            abrir_caso(doc_enviado)

st.title("Novo Documento Clínico")

st.info(
    "🔒 Documentos clínicos contêm **dados pessoais sensíveis** de saúde (LGPD, art. 5º, II "
    "e art. 11). Nesta fase use apenas documentos **sintéticos**; não envie dados reais de pacientes."
)

URL = envio.url_da_api()
if not envio.url_valida(URL):
    st.error("A variável de ambiente API_URL é inválida. Use http:// ou https://.")
    st.stop()
if envio.sem_https_fora_do_local(URL):
    st.warning(
        "A API não usa HTTPS: os dados trafegam sem criptografia. Não envie dados reais."
    )

canais = envio.carregar_canais()
if not canais:
    st.error("Não consegui ler os canais de origem em config/regras.json.")
    st.stop()

if "nd_documento_id" not in st.session_state:
    st.session_state["nd_documento_id"] = envio.novo_id()

# Resultado do último envio (agora apenas com a mensagem limpa, sem o link cru)
resultado = st.session_state.pop("nd_resultado", None)
if resultado:
    (st.success if resultado[0] else st.error)(resultado[1])

# H1.4.2 T3: aviso de ilegibilidade ("" = motivo não informado, usa a mensagem padrão)
aviso = st.session_state.get("nd_aviso")
if aviso is not None:
    st.warning(MENSAGEM_ILEGIBILIDADE.get(aviso, MENSAGEM_ILEGIBILIDADE_PADRAO))
    b1, b2 = st.columns(2)
    with b1:
        if st.button("📷 Enviar nova foto", key="nd_btn_nova_foto"):
            st.session_state.pop("nd_aviso", None)
            st.rerun()
    with b2:
        if st.button("📋 Enviar para revisão assim mesmo", key="nd_btn_revisao"):
            # O documento já está em recebidos/ e sendo processado; só descarta o aviso.
            st.session_state.pop("nd_aviso", None)
            st.session_state["nd_resultado"] = (
                True,
                "O documento foi encaminhado para a fila de revisão humana.",
            )
            st.rerun()

n = st.session_state.get("nd_n", 0)

with st.container(key="card_cadastro"):
    c1, c2 = st.columns(2)
    with c1:
        st.text_input(
            "ID do documento",
            key="nd_documento_id",
            max_chars=64,
            help="Identificador único gerado automaticamente. Letras, números, '_' ou '-'. "
            "Não use CPF, nome ou outro dado do paciente.",
        )
    with c2:
        st.selectbox(
            "Canal de origem",
            canais,
            key="nd_canal",
            help="De onde o documento chegou (Pronto-Socorro, Ambulatório, etc).",
        )

    aba_upload, aba_camera, aba_texto = st.tabs(["Upload", "Câmera", "Texto Direto"])

    with aba_upload:
        arquivo = st.file_uploader(
            f"Arraste o arquivo clínico aqui ({', '.join(FORMATOS_ACEITOS)})",
            type=None,
            key=f"nd_arquivo_{n}",
            max_upload_size=TAMANHO_MAXIMO_MB,
        )
        if arquivo is not None:
            if (arquivo.type or "").startswith("image/"):
                st.image(arquivo, caption=arquivo.name, width=400)
            else:
                st.caption(f"📄 {arquivo.name} ({arquivo.size // 1024} KB)")

    with aba_camera:
        if st.toggle("Ativar câmera", key=f"nd_cam_ligada_{n}"):
            foto = st.camera_input(
                "📷 Tirar foto com a câmera",
                key=f"nd_camera_{n}",
                help="Tire uma foto do documento com a câmera do seu dispositivo.",
            )
            if foto is not None:
                st.caption(
                    "✅ Foto capturada. Clique em **Enviar para Triagem** para processar."
                )
        else:
            st.caption("Ligue a câmera para fotografar o documento.")

    with aba_texto:
        st.text_area(
            "Texto do documento",
            key="nd_texto",
            height=250,
            placeholder="Cole aqui o texto do laudo, receita, guia, alta ou atestado.",
        )
        st.caption(
            "Se houver arquivo ou foto anexados, eles têm prioridade sobre o texto."
        )

    st.checkbox(
        "Confirmo que este documento contém apenas dados sintéticos (sem dados reais de pacientes).",
        key="nd_confirmo",
    )
    st.button("Enviar para Triagem", type="primary", on_click=_enviar, key="nd_enviar")
