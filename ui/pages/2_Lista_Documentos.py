import html
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import streamlit as st

# Garante importação dos módulos locais mesmo executando de diretórios diferentes
RAIZ_UI = Path(__file__).resolve().parents[1]
if str(RAIZ_UI) not in sys.path:
    sys.path.insert(0, str(RAIZ_UI))

from services.estilo import PAGINA_NOVO, pill, preparar_pagina
from services.http import timeout_api
from services.navegacao import abrir_caso

# ------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ------------------------------------------------------------------
st.set_page_config(page_title="Documentos · MediFlow", page_icon="🩺", layout="wide")
preparar_pagina()

API = os.getenv("API_URL", "http://localhost:8000")
CANAIS = ["Todos", "Pronto_Socorro", "Ambulatorio", "Laboratorio", "Operadora"]
POR_PAGINA = 5
FUSO_HORAS = (
    -3
)  # horário de Brasília; use None para mostrar o horário como a API devolveu

COR_PRIORIDADE = {
    "urgente": "red",
    "emergência": "red",
    "emergencia": "red",
    "alta": "orange",
    "rotina": "green",
    "baixa": "green",
}

# Larguras das 6 colunas da tabela
LARGURAS = [2.6, 2.1, 2.2, 1.3, 1.9, 1.3]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def cor_status(status: str) -> str:
    s = status.lower()
    if "erro" in s or "rejeit" in s:
        return "red"
    if "revis" in s or "pend" in s:
        return "yellow"
    if s == "processado":
        return "green"
    if "receb" in s or "process" in s or "fila" in s:
        return "blue"
    return "gray"


def rotulo_status(status: str) -> str:
    return status.replace("_", " ").capitalize()


def formatar_data(valor) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return texto[:16].replace("T", " ")
    if dt.tzinfo is not None and dt.timestamp() <= 0:
        return ""
    if dt.tzinfo is None and dt.year <= 1970 and dt.month == 1 and dt.day == 1:
        return ""
    if FUSO_HORAS is not None and dt.tzinfo is not None:
        dt = dt.astimezone(timezone(timedelta(hours=FUSO_HORAS)))
    return dt.strftime("%d/%m/%Y %H:%M")


def celula(texto, negrito: bool = False) -> str:
    """Texto de uma célula (escapado para HTML)."""
    peso = "font-weight:600;" if negrito else ""
    return f"<span style='font-size:.9rem;{peso}'>{html.escape(str(texto))}</span>"


def linha_pequena(texto: str) -> str:
    """Linha secundária em letra pequena: uma linha só, com reticências se for longa."""
    seguro = html.escape(texto)
    return (
        "<span style='display:block;font-size:.75rem;opacity:.7;overflow:hidden;"
        f"text-overflow:ellipsis;white-space:nowrap' title='{seguro}'>{seguro}</span>"
    )


def voltar_pagina_1() -> None:
    st.session_state["pagina"] = 1


def buscar_lista(canal: str) -> list | None:
    """GET /documentos. Devolve None se a API não respondeu."""
    params = {} if canal == "Todos" else {"canal_origem": canal}
    try:
        r = requests.get(f"{API}/documentos", params=params, timeout=timeout_api())
        r.raise_for_status()
        dados = r.json()
    except (requests.RequestException, ValueError):
        return None
    return dados if isinstance(dados, list) else None


@st.cache_data(ttl=60, show_spinner=False)
def buscar_motivo_rejeicao(doc_id: str) -> str:
    """Busca o motivo no detalhe caso o resumo da API devolva nulo."""
    try:
        r = requests.get(f"{API}/documentos/{doc_id}", timeout=timeout_api())
        if r.status_code == 200:
            dados = r.json()
            if dados.get("motivo_rejeicao"):
                return str(dados["motivo_rejeicao"]).strip()
            just = (dados.get("decisao_roteamento") or {}).get(
                "justificativa_roteamento"
            ) or ""
            if "Motivo:" in just:
                return just.split("Motivo:")[-1].strip()
    except (requests.RequestException, ValueError, KeyError):
        pass
    return ""


# ------------------------------------------------------------------
# CABEÇALHO (Título + Botão "+ Novo Documento")
# ------------------------------------------------------------------
col_tit, col_btn = st.columns([4, 1], vertical_alignment="bottom")
with col_tit:
    st.title("Documentos Clínicos")
    st.caption("Gerencie o repositório de laudos, receitas e guias enviados.")
with col_btn, st.container(key="btn_novo"):
    st.page_link(
        st.Page(f"{RAIZ_UI}/{PAGINA_NOVO}"),
        label="Novo Documento",
        icon=":material/add:",
        width="stretch",
    )

# ------------------------------------------------------------------
# FILTROS (pesquisa por texto + canal de origem)
# ------------------------------------------------------------------
col_busca, col_canal = st.columns([3, 1], vertical_alignment="bottom")

with col_busca:
    busca = st.text_input(
        "Pesquisar",
        key="busca_docs",
        placeholder="Pesquisar por ID, tipo de documento ou destino",
        icon=":material/search:",
        label_visibility="collapsed",
        on_change=voltar_pagina_1,
    )

with col_canal:
    canal = st.selectbox(
        "Canal de origem",
        CANAIS,
        label_visibility="collapsed",
        on_change=voltar_pagina_1,
        help="Filtrar por canal de origem",
    )

# ------------------------------------------------------------------
# CONSULTA AO BACKEND (GET /documentos)
# ------------------------------------------------------------------
itens_api = buscar_lista(canal)
if itens_api is None:
    st.error("Não consegui conectar com a API. Verifique se ela está no ar.")
    st.stop()
if not itens_api:
    st.info("Nenhum documento encontrado para este canal de origem.")
    st.stop()


def motivo_de(item: dict) -> str:
    motivo = item.get("motivo_rejeicao")
    texto = str(motivo).strip() if motivo is not None else ""
    return "" if texto.lower() == "none" else texto


DOCUMENTOS = [
    {
        "id": str(item.get("documento_id", "—")),
        "tipo": item.get("tipo_documento") or "Não classificado",
        "destino": item.get("destino") or item.get("canal_origem") or "—",
        "prioridade": item.get("nivel_prioridade") or "Rotina",
        "status": str(item.get("status") or "processado"),
        "canal_origem": item.get("canal_origem", ""),
        "data_bruta": str(item.get("data") or ""),
        "motivo": motivo_de(item),
    }
    for item in itens_api
    if isinstance(item, dict)
]
DOCUMENTOS.sort(key=lambda d: d["data_bruta"], reverse=True)  # mais recentes primeiro

termo = busca.strip().lower()
filtrados = [
    d
    for d in DOCUMENTOS
    if not termo
    or termo
    in (
        f"{d['id']} {d['tipo']} {d['destino']} {d['status']} "
        f"{d['canal_origem']} {d['motivo']}"
    ).lower()
]

# ------------------------------------------------------------------
# LISTA COM PAGINAÇÃO
# ------------------------------------------------------------------
total_paginas = max(1, math.ceil(len(filtrados) / POR_PAGINA))
pagina = min(st.session_state.get("pagina", 1), total_paginas)

inicio = (pagina - 1) * POR_PAGINA
itens = filtrados[inicio : inicio + POR_PAGINA]

with st.container(key="card_lista"):
    if not itens:
        st.info("Nenhum documento encontrado com o termo pesquisado.")
    else:
        cab = st.columns(LARGURAS)
        titulos = [
            "ID / Data",
            "Tipo de Documento",
            "Destino / Origem",
            "Prioridade",
            "Status",
            "Ação",
        ]
        for col, texto in zip(cab, titulos):
            col.markdown(
                f"<b style='font-size:.85rem'>{texto}</b>", unsafe_allow_html=True
            )
        st.markdown(
            "<hr style='margin:.25rem 0 .5rem;opacity:.3'>", unsafe_allow_html=True
        )

        for d in itens:
            c1, c2, c3, c4, c5, c6 = st.columns(LARGURAS, vertical_alignment="center")

            data_txt = formatar_data(d["data_bruta"])
            c1.markdown(
                celula(d["id"], negrito=True)
                + (linha_pequena(data_txt) if data_txt else ""),
                unsafe_allow_html=True,
            )
            c2.markdown(celula(d["tipo"]), unsafe_allow_html=True)
            c3.markdown(
                celula(str(d["destino"]).replace("_", " ")), unsafe_allow_html=True
            )
            c4.markdown(
                pill(
                    html.escape(str(d["prioridade"])),
                    COR_PRIORIDADE.get(str(d["prioridade"]).lower(), "gray"),
                ),
                unsafe_allow_html=True,
            )
            motivo = d["motivo"]
            if not motivo and d["status"].lower() == "rejeitado":
                motivo = buscar_motivo_rejeicao(d["id"])

            c5.markdown(
                pill(html.escape(rotulo_status(d["status"])), cor_status(d["status"]))
                + (linha_pequena(f"Motivo: {motivo}") if motivo else ""),
                unsafe_allow_html=True,
            )
            if c6.button(
                "Abrir",
                key=f"lista_abrir_{d['id']}",
                type="primary",
                icon=":material/open_in_new:",
                width="stretch",
                help="Abrir no Dashboard",
            ):
                abrir_caso(d["id"])  # porta única: guarda o caso e vai ao Dashboard

            st.markdown(
                "<hr style='margin:.4rem 0;opacity:.15'>", unsafe_allow_html=True
            )

        # Paginação
        _, p1, p2, p3, _ = st.columns([3, 1, 2, 1, 3], vertical_alignment="center")
        with p1:
            if st.button(
                "",
                icon=":material/chevron_left:",
                disabled=pagina <= 1,
                key="pg_ant",
                width="stretch",
            ):
                st.session_state["pagina"] = pagina - 1
                st.rerun()
        with p2:
            st.markdown(
                f"<div style='text-align:center'>Página {pagina} de {total_paginas}</div>",
                unsafe_allow_html=True,
            )
        with p3:
            if st.button(
                "",
                icon=":material/chevron_right:",
                disabled=pagina >= total_paginas,
                key="pg_prox",
                width="stretch",
            ):
                st.session_state["pagina"] = pagina + 1
                st.rerun()
