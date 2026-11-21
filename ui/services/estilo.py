import sys
from pathlib import Path

import streamlit as st

RAIZ_UI = Path(__file__).resolve().parents[1]
CAMINHO_LOGO = RAIZ_UI / "assets" / "logo.png"

PAGINA_LISTA = "pages/2_Lista_Documentos.py"
PAGINA_NOVO = "pages/1_Novo_Documento.py"
PAGINA_DASHBOARD = "pages/3_Dashboard.py"
PAGINA_FILA = "pages/6_Fila_de_Revisao.py"
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

    /* Fila de revisão: faixa pela prioridade e botões azuis */
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

    /* Fila de revisão: "Abrir caso" é secundário (contorno azul). Vem depois da regra
       acima e é mais específico, por isso vence. */
    div[class*="st-key-card_fila_"] div[class*="st-key-fila_abrir_"] button {
        background: transparent !important;
        border: 1px solid #3B82F6 !important;
    }
    div[class*="st-key-card_fila_"] div[class*="st-key-fila_abrir_"] button:hover {
        background: rgba(59, 130, 246, .12) !important;
    }
    div[class*="st-key-card_fila_"] div[class*="st-key-fila_abrir_"] button * {
        color: #3B82F6 !important;
    }

    /* Botão secundário "Voltar": contorno azul, sem preenchimento */
    div[class*="st-key-btn_voltar"] a[data-testid="stPageLink-NavLink"] {
        border: 1px solid #3B82F6;
        border-radius: 8px;
        min-height: 2.5rem;
        justify-content: center;
        padding: 0.5rem 1rem;
        transition: background .15s;
    }
    div[class*="st-key-btn_voltar"] a[data-testid="stPageLink-NavLink"]:hover {
        background: rgba(59, 130, 246, .12);
    }
    div[class*="st-key-btn_voltar"] a[data-testid="stPageLink-NavLink"] *,
    div[class*="st-key-btn_voltar"] a[data-testid="stPageLink-NavLink"] p,
    div[class*="st-key-btn_voltar"] a[data-testid="stPageLink-NavLink"] span {
        color: #3B82F6 !important;
        font-weight: 600;
    }
</style>
"""

# Só é aplicado na página "Revisão do caso" da equipe: estilo, sem mexer no conteúdo.
CSS_REVISAO = """
<style>
    /* Original e Extração viram dois cards do mesmo tamanho */
    .block-container > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] {
        align-items: stretch !important;
    }
    .block-container > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"]
        > :is([data-testid="stColumn"], [data-testid="column"]) {
        box-sizing: border-box;
        min-width: 0;
        background: color-mix(in srgb, currentColor 7%, transparent);
        background: rgb(from currentColor 255 255 255 / calc(1 - r / 255));
        border: 1px solid rgba(128, 128, 128, .25);
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
        padding: 1.1rem 1.25rem;
    }
    /* Os blocos seguintes (ex.: Decisão da Auditora) não viram card */
    .block-container > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"]
        ~ [data-testid="stHorizontalBlock"]
        > :is([data-testid="stColumn"], [data-testid="column"]) {
        background: transparent;
        border: none;
        box-shadow: none;
        padding: 0;
    }

    /* Títulos de seção no mesmo estilo dos títulos dos cards */
    .block-container h3 {
        font-size: .95rem; font-weight: 700; letter-spacing: .02em;
        text-transform: uppercase; padding: .75rem 0 .25rem;
    }
    .block-container hr { margin: 1.5rem 0; opacity: .3; }

    /* Trilha de decisões: expansores como cartões */
    [data-testid="stExpander"] {
        border: 1px solid rgba(128, 128, 128, .25);
        border-radius: 10px;
        background: color-mix(in srgb, currentColor 7%, transparent);
        background: rgb(from currentColor 255 255 255 / calc(1 - r / 255));
    }
</style>
"""

# Só é aplicado na página "Configurações" (da equipe): estilo, sem mexer no conteúdo.
CSS_CONFIG = """
<style>
    /* Métricas do topo viram cards */
    [data-testid="stMetric"] {
        background: color-mix(in srgb, currentColor 7%, transparent);
        background: rgb(from currentColor 255 255 255 / calc(1 - r / 255));
        border: 1px solid rgba(128, 128, 128, .25);
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
        padding: 1rem 1.25rem;
    }
    [data-testid="stMetricLabel"] {
        font-size: .8rem; opacity: .75; text-transform: uppercase; letter-spacing: .03em;
    }
    [data-testid="stMetricValue"] { font-size: 1.7rem; font-weight: 700; }

    /* Títulos das seções: barra azul à esquerda, no lugar das divisórias soltas */
    .block-container h3 {
        font-size: 1.05rem; font-weight: 700; letter-spacing: .02em;
        text-transform: uppercase;
        border-left: 4px solid #2563EB;
        padding: .15rem 0 .15rem .7rem;
        margin-top: .5rem;
    }
    .block-container h4, .block-container h5 {
        font-size: .95rem; font-weight: 700; letter-spacing: .02em;
    }
    .block-container hr { margin: 1.75rem 0; opacity: .25; }

    /* Slider, formulário, tabelas e expansor como cartões */
    [data-testid="stSlider"],
    [data-testid="stForm"],
    [data-testid="stExpander"] {
        background: color-mix(in srgb, currentColor 7%, transparent);
        background: rgb(from currentColor 255 255 255 / calc(1 - r / 255));
        border: 1px solid rgba(128, 128, 128, .25);
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
    }
    [data-testid="stSlider"] { padding: 1rem 1.5rem .5rem; }
    [data-testid="stForm"] { padding: 1.25rem 1.5rem; }
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(128, 128, 128, .25);
        border-radius: 10px;
        overflow: hidden;
    }

    /* Botão secundário (ex.: "Restaurar versão selecionada"): contorno azul */
    button[data-testid="stBaseButton-secondary"],
    button[kind="secondary"] {
        background: transparent !important;
        border: 1px solid #3B82F6 !important;
        border-radius: 8px;
        transition: background .15s;
    }
    button[data-testid="stBaseButton-secondary"]:hover,
    button[kind="secondary"]:hover {
        background: rgba(59, 130, 246, .12) !important;
    }
    button[data-testid="stBaseButton-secondary"] *,
    button[kind="secondary"] * {
        color: #3B82F6 !important;
        font-weight: 600;
    }
</style>
"""


def _e_revisao_de_caso(nome_arquivo: str) -> bool:
    """A página 'Revisão do caso' da equipe (não a 'Fila' nem a versão nova 'UI_')."""
    nome = nome_arquivo.lower()
    return "revisao" in nome and "fila" not in nome and "ui_" not in nome


def _e_configuracoes(nome_arquivo: str) -> bool:
    """A página 'Configurações' (antes 'Regras')."""
    return "configuracoes" in nome_arquivo.lower()


def _barra_revisao() -> None:
    """Navegação no topo da Revisão do caso da equipe: voltar à fila e abrir o caso no Dashboard."""
    doc_id = str(st.query_params.get("id") or "").strip()
    fila_existe = (RAIZ_UI / PAGINA_FILA).exists()
    with st.container(key="barra_revisao"):
        c1, c2, _ = st.columns([2, 2.4, 5], vertical_alignment="center")
        if fila_existe:
            with c1, st.container(key="btn_voltar"):
                st.page_link(
                    PAGINA_FILA,
                    label="Voltar para a Fila",
                    icon=":material/arrow_back:",
                )
        if doc_id:
            with c2:
                if st.button(
                    "Ver caso no Dashboard",
                    key="rev_ver_dashboard_equipe",
                    type="primary",
                    icon=":material/open_in_new:",
                    width="stretch",
                ):
                    from services.navegacao import abrir_caso  # evita import circular

                    abrir_caso(doc_id)


def preparar_pagina(estilo_especifico: bool = True) -> None:
    """Logo, sidebar e CSS padrão. Chame logo depois do st.set_page_config.

    estilo_especifico=False desliga os estilos que só valem para as páginas da equipe
    (Revisão do caso e Configurações). As páginas novas passam False e cuidam do próprio layout.
    """
    # Arquivo da página que chamou (usado para estilos específicos de uma tela)
    chamador = Path(sys._getframe(1).f_globals.get("__file__", "")).name

    # Devolve à URL o ID do caso que a navegação marcou (o switch_page limpa a URL)
    pendente = st.session_state.pop("_id_para_url", None)
    if pendente and not st.query_params.get("id"):
        st.query_params["id"] = pendente

    if CAMINHO_LOGO.exists():
        st.logo(str(CAMINHO_LOGO), size="large")
    st.markdown(CSS, unsafe_allow_html=True)

    pagina_config = RAIZ_UI / PAGINA_CONFIG
    if pagina_config.exists():
        # O item sai da lista do menu e passa a ficar só no rodapé
        st.markdown(
            """
<style>
    [data-testid="stSidebarNav"] li:has(a[href$="Configuracoes"]) { display: none; }
    [data-testid="stSidebarNav"] a[href$="Configuracoes"] { display: none; }

    /* Oculta Revisao de Caso do menu lateral */
    [data-testid="stSidebarNav"] li:has(a[href*="Revisao_de_Caso"]) { display: none; }
    [data-testid="stSidebarNav"] a[href*="Revisao_de_Caso"] { display: none; }
</style>
""",
            unsafe_allow_html=True,
        )

    with st.sidebar:
        st.markdown("<div style='height: 35vh;'></div>", unsafe_allow_html=True)
        st.divider()
        if pagina_config.exists():
            # st.page_link(PAGINA_CONFIG, label="Configurações", icon=":material/settings:")
            st.page_link(
                st.Page(f"{RAIZ_UI}/{PAGINA_CONFIG}"),
                label="Configurações",
                icon=":material/settings:",
            )
        else:
            st.caption("⚙️ Configurações")

    if not estilo_especifico:
        return
    if _e_revisao_de_caso(chamador):
        st.markdown(CSS_REVISAO, unsafe_allow_html=True)
        _barra_revisao()
    elif _e_configuracoes(chamador):
        st.markdown(CSS_CONFIG, unsafe_allow_html=True)


def pill(texto: str, cor: str = "gray") -> str:
    return f'<span class="pill {cor}">{texto}</span>'
