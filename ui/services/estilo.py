from pathlib import Path

import streamlit as st

CAMINHO_LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo.png"

PAGINA_LISTA = "pages/2_Lista_Documentos.py"
PAGINA_NOVO = "pages/1_Novo_Documento.py"
PAGINA_DASHBOARD = "pages/3_Dashboard.py"
PAGINA_CONFIG = "pages/99_Configuracoes.py"

CSS = """
<style>
    [data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 5rem; max-width: 1400px; }
    [data-testid="stLogo"] { height: 3.5rem !important; }
    [data-testid="stLogo"] img {
        height: 3.5rem !important; max-height: 3.5rem !important; width: auto !important;
    }

    div[class*="st-key-card_"] {
        background: color-mix(in srgb, currentColor 7%, transparent);
        background: rgb(from currentColor 255 255 255 / calc(1 - r / 255));
        border: 1px solid rgba(128, 128, 128, .25);
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
        padding: 1.1rem 1.25rem;
    }

    /* Pílulas */
    .pill {
        display: inline-block; padding: 2px 12px; border-radius: 999px;
        font-size: 0.78rem; font-weight: 600; white-space: nowrap;
    }
    .pill.red    { background: rgba(239, 68, 68, .16);  color: #EF4444; }
    .pill.green  { background: rgba(34, 197, 94, .16);  color: #16A34A; }
    .pill.orange { background: rgba(249, 115, 22, .16); color: #F97316; }
    .pill.blue   { background: rgba(59, 130, 246, .16); color: #3B82F6; }
    .pill.yellow { background: rgba(234, 179, 8, .2);   color: #CA8A04; }
    .pill.gray   { background: rgba(128, 128, 128, .14); color: inherit;
                   border: 1px solid rgba(128, 128, 128, .3); }

    /* Tabela da lista */
    .tabela-wrap { overflow-x: auto; }
    table.docs { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
    table.docs th {
        text-align: left; padding: 10px 12px; font-weight: 700;
        border-bottom: 2px solid rgba(128, 128, 128, .3);
    }
    table.docs td {
        padding: 12px; border-bottom: 1px solid rgba(128, 128, 128, .2);
    }
    table.docs tr:last-child td { border-bottom: none; }

    /* Área de arrastar arquivo */
    [data-testid="stFileUploaderDropzone"] {
        border: 2px dashed #3B82F6;
        background: rgba(59, 130, 246, .07);
        border-radius: 10px;
        padding: 1.5rem;
    }

    /* Botão "Novo Documento" em destaque */
    div[class*="st-key-btn_novo"] a[data-testid="stPageLink-NavLink"] {
        background: #2563EB !important;
        border-radius: 8px;
        min-height: 2.5rem;
        justify-content: center;
        padding: 0.5rem 1rem;
        transition: background .15s;
    }
    div[class*="st-key-btn_novo"] a[data-testid="stPageLink-NavLink"]:hover {
        background: #1D4ED8 !important;
    }
    div[class*="st-key-btn_novo"] a[data-testid="stPageLink-NavLink"] *,
    div[class*="st-key-btn_novo"] a[data-testid="stPageLink-NavLink"] p,
    div[class*="st-key-btn_novo"] a[data-testid="stPageLink-NavLink"] span {
        color: #FFFFFF !important;
        font-weight: 600;
    }

    /* Botões de urgência (Home) */
    div[class*="st-key-urg_"] button {
        height: 6rem; justify-content: flex-start; text-align: left;
        padding: .75rem 1rem; border-radius: 12px;
        border-left-width: 6px; border-color: rgba(128, 128, 128, .25);
        box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
    }
    div[class*="st-key-urg_"] button p { font-size: .85rem; margin: 0; }
    div[class*="st-key-urg_"] button p:last-child { font-size: 2rem; font-weight: 600; }
    div[class*="st-key-urg_U"] button { border-left-color: #EF4444; }
    div[class*="st-key-urg_A"] button { border-left-color: #EAB308; }
    div[class*="st-key-urg_R"] button { border-left-color: #22C55E; }

    /* Gráfico de barras (Home) */
    .barras { display: flex; align-items: flex-end; justify-content: space-around;
              height: 160px; border-bottom: 1px solid rgba(128, 128, 128, .4); }
    .barra-col { display: flex; flex-direction: column; align-items: center;
                 justify-content: flex-end; width: 28%; height: 100%; }
    .barra-col b { font-size: .9rem; margin-bottom: 4px; }
    .barra-col div { width: 100%; border-radius: 4px 4px 0 0; }
    .barras-rotulos { display: flex; justify-content: space-around;
                      font-size: .8rem; opacity: .7; padding-top: 6px; }
    .barras-rotulos span { width: 28%; text-align: center; }

    /* Fila de revisão: faixa pela prioridade e botão azul de abrir caso */
    div[class*="st-key-card_fila_red"]    { border-left: 5px solid #EF4444; }
    div[class*="st-key-card_fila_orange"] { border-left: 5px solid #F97316; }
    div[class*="st-key-card_fila_green"]  { border-left: 5px solid #22C55E; }
    div[class*="st-key-card_fila_gray"]   { border-left: 5px solid #94A3B8; }

    div[class*="st-key-card_fila_"] button,
    div[class*="st-key-card_fila_"] a[data-testid="stPageLink-NavLink"] {
        background: #2563EB !important;
        border: none;
        border-radius: 8px;
        min-height: 2.5rem;
        transition: background .15s;
    }
    div[class*="st-key-card_fila_"] button:hover,
    div[class*="st-key-card_fila_"] a[data-testid="stPageLink-NavLink"]:hover {
        background: #1D4ED8 !important;
    }
    div[class*="st-key-card_fila_"] button *,
    div[class*="st-key-card_fila_"] a[data-testid="stPageLink-NavLink"] * {
        color: #FFFFFF !important;
        font-weight: 600;
    }
</style>
"""


def preparar_pagina() -> None:
    """Logo, sidebar e CSS padrão. Chame logo depois do st.set_page_config."""
    # Devolve à URL o ID do caso que a navegação marcou (o switch_page limpa a URL)
    pendente = st.session_state.pop("_id_para_url", None)
    if pendente and not st.query_params.get("id"):
        st.query_params["id"] = pendente

    if CAMINHO_LOGO.exists():
        st.logo(str(CAMINHO_LOGO), size="large")
    st.markdown(CSS, unsafe_allow_html=True)

    pagina_config = Path(__file__).resolve().parents[1] / PAGINA_CONFIG
    if pagina_config.exists():
        # O item sai da lista do menu e passa a ficar só no rodapé
        st.markdown(
            """
<style>
    [data-testid="stSidebarNav"] li:has(a[href$="Configuracoes"]) { display: none; }
    [data-testid="stSidebarNav"] a[href$="Configuracoes"] { display: none; }
</style>
""",
            unsafe_allow_html=True,
        )

    with st.sidebar:
        st.markdown("<div style='height: 35vh;'></div>", unsafe_allow_html=True)
        st.divider()
        if pagina_config.exists():
            st.page_link(PAGINA_CONFIG, label="Configurações", icon=":material/settings:")
        else:
            st.caption("⚙️ Configurações")


def pill(texto: str, cor: str = "gray") -> str:
    return f'<span class="pill {cor}">{texto}</span>'