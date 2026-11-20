import html
import os
import sys
from collections import Counter
from pathlib import Path

import requests
import streamlit as st

# Garante o sys.path correto
RAIZ_UI = Path(__file__).resolve().parent
if str(RAIZ_UI) not in sys.path:
    sys.path.insert(0, str(RAIZ_UI))

from services.estilo import PAGINA_FILA, PAGINA_LISTA, pill, preparar_pagina
from services.navegacao import abrir_caso

try:
    from componentes.fila import minutos_de_espera, texto_espera
except ImportError:  # sem o componente, a faixa só não mostra o tempo de espera
    minutos_de_espera = texto_espera = None

st.set_page_config(page_title="Home · MediFlow", page_icon="🩺", layout="wide")
preparar_pagina()

API = os.getenv("API_URL", "http://localhost:8000")

# Mostra, no fim da página, os valores reais que a API devolve (só para testes).
MOSTRAR_DIAGNOSTICO = False

# Ajuste fino do alinhamento dos dois cards (em pixels)
# Se a lista (com 5 casos) ficar maior que o gráfico, aumente ALTURA_CARDS;
# se ficar menor, diminua. Mexa de 10 em 10.
ALTURA_CARDS = 430  # altura mínima do gráfico e da lista de casos
ALTURA_BARRAS = 280  # altura da área das barras (acompanhe ALTURA_CARDS)

# ------------------------------------------------------------------
# CONFIGURAÇÃO DE URGÊNCIAS E CORES (MEDIFLOW DESIGN SPEC)
# ------------------------------------------------------------------
URGENCIAS = {
    "U": {"nome": "Urgente", "cor": "#EF4444", "pill": "red"},
    "A": {"nome": "Em revisão", "cor": "#EAB308", "pill": "yellow"},
    "R": {"nome": "Rotina", "cor": "#22C55E", "pill": "green"},
}
# Dica que aparece ao passar o mouse em cada botão
DICAS = {
    "U": "Casos com prioridade urgente ou destinados à fila de emergência.",
    "A": "Casos em revisão humana ou com prioridade alta.",
    "R": "Casos de rotina, seguindo o fluxo normal.",
}
# Casos que não cabem nas três (sem prioridade, em processamento, erro, rejeitado)
OUTROS = {"nome": "Outros", "cor": "#94A3B8", "pill": "gray"}
POR_TELA = 5

ss = st.session_state
filtro = ss.get("filtro_urgencia")  # None, "U", "A" ou "R"
if filtro not in URGENCIAS:
    filtro = None


def alternar_filtro(chave: str) -> None:
    ss["filtro_urgencia"] = None if ss.get("filtro_urgencia") == chave else chave


# Estilo desta tela: cards do mesmo tamanho, barras altas e células sem quebra de linha
st.markdown(
    f"""
<style>
    div[class*="st-key-card_grafico"], div[class*="st-key-card_casos"] {{
        min-height: {ALTURA_CARDS}px;
    }}
    div[class*="st-key-card_home_revisao"] {{ border-left: 5px solid #EAB308; }}
    .barras {{ height: {ALTURA_BARRAS}px; }}
    .celula {{
        display: block; overflow: hidden; text-overflow: ellipsis;
        white-space: nowrap; font-size: .85rem;
    }}
</style>
""",
    unsafe_allow_html=True,
)

# Destaque visual do botão selecionado
if filtro:
    st.markdown(
        f"<style>div[class*='st-key-urg_{filtro}'] button "
        f"{{ border: 2px solid {URGENCIAS[filtro]['cor']}; border-left-width: 6px; }}</style>",
        unsafe_allow_html=True,
    )


def celula(texto, negrito: bool = False) -> str:
    """Texto de uma célula da lista: uma linha só, com reticências se for longo."""
    seguro = html.escape(str(texto))
    peso = "font-weight:600" if negrito else ""
    return f'<span class="celula" style="{peso}" title="{seguro}">{seguro}</span>'


# ------------------------------------------------------------------
# CLASSIFICAÇÃO DOS CASOS NAS CATEGORIAS DA HOME
# ------------------------------------------------------------------
PRIO_URGENTE = ("urgente", "emergência", "emergencia", "critico", "crítico")
PRIO_ALTA = ("alta", "atenção", "atencao")
PRIO_ROTINA = ("rotina", "baixa")


def classificar_urgencia(doc: dict) -> str:
    """U, A, R ou O (outros). Em dúvida, não vira Rotina."""
    prio = str(doc.get("nivel_prioridade") or "").strip().lower()
    destino = str(doc.get("destino") or "").strip().lower()
    status = str(doc.get("status") or "").strip().lower()

    # Casos encerrados ou que falharam não pedem atenção
    if "rejeit" in status or "erro" in status:
        return "O"
    if prio in PRIO_URGENTE or "emerg" in destino:
        return "U"
    # Revisão humana: o status real da API é "em_auditoria_humana"
    if (
        prio in PRIO_ALTA
        or "revis" in destino
        or "revis" in status
        or "auditoria" in status
    ):
        return "A"
    if "processando" in status or "recebido" in status:
        return "O"
    if prio in PRIO_ROTINA:
        return "R"
    return "O"


# ------------------------------------------------------------------
# CARREGAMENTO DOS DADOS REAIS DO BACKEND
# ------------------------------------------------------------------
@st.cache_data(ttl=15, show_spinner=False)
def buscar_documentos() -> list:
    r = requests.get(f"{API}/documentos", timeout=15)
    r.raise_for_status()
    dados = r.json()
    if not isinstance(dados, list):
        raise TypeError("resposta inesperada")
    return [d for d in dados if isinstance(d, dict)]


@st.cache_data(ttl=15, show_spinner=False)
def buscar_fila() -> list:
    """GET /filas/revisao: a mesma fonte da tela Fila de Revisão."""
    r = requests.get(f"{API}/filas/revisao", timeout=5)
    r.raise_for_status()
    dados = r.json()
    if not isinstance(dados, list):
        raise TypeError("resposta inesperada")
    return [c for c in dados if isinstance(c, dict)]


try:
    documentos_brutos = buscar_documentos()
except (requests.RequestException, ValueError):
    st.title("Home")
    st.error("Não foi possível carregar os casos. Verifique se a API está no ar.")
    st.stop()

CONTAGENS = {"U": 0, "A": 0, "R": 0}
OUTROS_TOTAL = 0
CASOS = []

for item in documentos_brutos:
    cat = classificar_urgencia(item)
    if cat in CONTAGENS:
        CONTAGENS[cat] += 1
    else:
        OUTROS_TOTAL += 1
    CASOS.append(
        {
            "id": str(item.get("documento_id") or "—"),
            "tipo": item.get("tipo_documento") or "Não classificado",
            "destino": item.get("destino") or item.get("canal_origem") or "—",
            "urg": cat,
            "data": str(item.get("data") or ""),
        }
    )

CASOS.sort(key=lambda c: c["data"], reverse=True)  # mais recentes primeiro

# Faixa "Aguardando revisão humana": usa a mesma fonte da Fila de Revisão
try:
    fila_casos = buscar_fila()
except (requests.RequestException, ValueError):
    fila_casos = None

if fila_casos is None:
    qtd_fila = CONTAGENS["A"]  # fila fora do ar: usa a contagem do botão
    mais_antigo = None
else:
    qtd_fila = len(fila_casos)
    mais_antigo = None
    chegadas = [str(c["chegada_em"]) for c in fila_casos if c.get("chegada_em")]
    if chegadas and minutos_de_espera and texto_espera:
        try:
            mais_antigo = texto_espera(minutos_de_espera(min(chegadas)))
        except Exception:  # noqa: BLE001 - o tempo de espera é opcional
            mais_antigo = None

# ------------------------------------------------------------------
# CABEÇALHO E BOTÕES DE URGÊNCIA
# ------------------------------------------------------------------
st.title("Home")
st.caption(
    "Visão geral dos casos em triagem. Clique em uma urgência para filtrar a lista."
)

colunas = st.columns(3, gap="medium")
for coluna, (chave, u) in zip(colunas, URGENCIAS.items()):
    with coluna:
        st.button(
            f"{u['nome']}\n\n{CONTAGENS[chave]}",
            key=f"urg_{chave}",
            on_click=alternar_filtro,
            args=(chave,),
            help=DICAS[chave],
            use_container_width=True,
        )

# ------------------------------------------------------------------
# FAIXA: CASOS AGUARDANDO REVISÃO HUMANA (porta de entrada da Fila)
# ------------------------------------------------------------------
st.write("")
if qtd_fila > 0:
    with st.container(key="card_home_revisao"):
        c_txt, c_btn = st.columns([5, 2], vertical_alignment="center")
        if mais_antigo:
            sub = f"O mais antigo espera há {html.escape(str(mais_antigo))}."
        else:
            sub = "Esses casos precisam de uma decisão da auditora."
        c_txt.markdown(
            '<div style="display:flex;align-items:baseline;gap:.75rem;flex-wrap:wrap">'
            f'<span style="font-size:1.8rem;font-weight:700">{qtd_fila}</span>'
            '<span style="font-size:1rem;font-weight:600">'
            "caso(s) aguardando revisão humana</span></div>"
            f'<p style="margin:.2rem 0 0;font-size:.85rem;opacity:.75">{sub}</p>',
            unsafe_allow_html=True,
        )
        if c_btn.button(
            "Ir para a Fila de Revisão",
            key="home_ir_fila",
            type="primary",
            icon=":material/arrow_forward:",
            use_container_width=True,
        ):
            st.switch_page(PAGINA_FILA)
else:
    st.caption("Nenhum caso aguardando revisão humana no momento.")

st.write("")
col_graf, col_lista = st.columns([5, 7], gap="large")

# ------------------------------------------------------------------
# GRÁFICO DE BARRAS
# ------------------------------------------------------------------
with col_graf, st.container(key="card_grafico"):
    total_geral = sum(CONTAGENS.values()) + OUTROS_TOTAL
    maximo = max(CONTAGENS.values()) or 1  # evita divisão por zero se vazio
    altura_max = ALTURA_BARRAS - 40  # sobra espaço para o número acima da barra

    barras = "".join(
        f'<div class="barra-col"><b>{CONTAGENS[k]}</b>'
        f'<div style="height:{round(CONTAGENS[k] / maximo * altura_max)}px;background:{u["cor"]}"></div></div>'
        for k, u in URGENCIAS.items()
    )
    rotulos = "".join(f"<span>{u['nome']}</span>" for u in URGENCIAS.values())
    nota_outros = (
        f" · <b>{OUTROS_TOTAL}</b> em outros "
        "(sem prioridade, em processamento, com erro ou rejeitados)"
        if OUTROS_TOTAL
        else ""
    )

    st.markdown(
        '<p class="card-title" style="font-weight:700;margin:0 0 12px">CASOS POR URGÊNCIA</p>'
        f'<div class="barras">{barras}</div>'
        f'<div class="barras-rotulos">{rotulos}</div>'
        f'<p style="font-size:.8rem;opacity:.7;margin-top:10px">'
        f"Total: <b>{total_geral}</b> casos no sistema{nota_outros}</p>",
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------------
# LISTA DE CASOS
# ------------------------------------------------------------------
with col_lista, st.container(key="card_casos"):
    titulo = (
        f"CASOS: {URGENCIAS[filtro]['nome'].upper()}" if filtro else "CASOS RECENTES"
    )
    c_tit, c_limpar = st.columns([3, 1], vertical_alignment="center")
    c_tit.markdown(
        f'<p style="font-weight:700;margin:0">{titulo}</p>', unsafe_allow_html=True
    )
    if filtro:
        c_limpar.button(
            "Limpar filtro", on_click=alternar_filtro, args=(filtro,), key="limpar"
        )

    candidatos = [c for c in CASOS if not filtro or c["urg"] == filtro]
    visiveis = candidatos[:POR_TELA]
    largura = [3.2, 2.5, 2.6, 1.7, 1.4]

    cab = st.columns(largura)
    for col, texto in zip(cab, ["ID", "Tipo", "Destino / Origem", "Urgência", ""]):
        col.markdown(
            f"<span style='font-size:.8rem;opacity:.7'>{texto}</span>",
            unsafe_allow_html=True,
        )

    if not visiveis:
        st.info("Nenhum caso encontrado para este critério.")
    else:
        for caso in visiveis:
            c1, c2, c3, c4, c5 = st.columns(largura, vertical_alignment="center")
            u = URGENCIAS.get(caso["urg"], OUTROS)
            c1.markdown(celula(caso["id"], negrito=True), unsafe_allow_html=True)
            c2.markdown(celula(caso["tipo"]), unsafe_allow_html=True)
            c3.markdown(
                celula(str(caso["destino"]).replace("_", " ")), unsafe_allow_html=True
            )
            c4.markdown(pill(u["nome"], u["pill"]), unsafe_allow_html=True)
            if c5.button(
                "Abrir",
                key=f"abrir_home_{caso['id']}",
                type="primary",
                use_container_width=True,
                help="Abrir no Dashboard",
            ):
                abrir_caso(caso["id"])  # porta única: guarda o caso e vai ao Dashboard

    total_filtro = CONTAGENS[filtro] if filtro else total_geral
    st.markdown("<hr style='margin:.5rem 0 .3rem;opacity:.15'>", unsafe_allow_html=True)
    rodape, link = st.columns([2, 3], vertical_alignment="center")
    rodape.caption(f"Mostrando {len(visiveis)} de {total_filtro}")
    with link, st.container(key="btn_voltar_ver_todos"):
        st.page_link(
            PAGINA_LISTA,
            label="Ver todos em Documentos",
            icon=":material/arrow_forward:",
            use_container_width=True,
        )

# ------------------------------------------------------------------
# DIAGNÓSTICO (só para testes: MOSTRAR_DIAGNOSTICO = True)
# ------------------------------------------------------------------
if MOSTRAR_DIAGNOSTICO:
    st.write("")
    with st.container(key="card_diagnostico"):
        st.markdown(
            '<p class="card-title" style="font-weight:700;margin:0">'
            "DIAGNÓSTICO DAS CATEGORIAS (TEMPORÁRIO)</p>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Cada linha é uma combinação de valores que a API devolveu, "
            "com a categoria em que a Home a colocou."
        )
        nomes = {**{k: v["nome"] for k, v in URGENCIAS.items()}, "O": OUTROS["nome"]}
        combinacoes = Counter(
            (
                str(d.get("nivel_prioridade") or "—"),
                str(d.get("destino") or "—"),
                str(d.get("status") or "—"),
                nomes[classificar_urgencia(d)],
            )
            for d in documentos_brutos
        )
        st.dataframe(
            [
                {
                    "Prioridade": p,
                    "Destino": de,
                    "Status": s,
                    "Categoria na Home": c,
                    "Qtd": n,
                }
                for (p, de, s, c), n in sorted(combinacoes.items(), key=lambda x: -x[1])
            ],
            hide_index=True,
        )
