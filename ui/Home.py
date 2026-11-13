import streamlit as st

from services.estilo import PAGINA_DASHBOARD, PAGINA_LISTA, pill, preparar_pagina

st.set_page_config(page_title="Home · MediFlow", page_icon="🩺", layout="wide")
preparar_pagina()

# ------------------------------------------------------------------
# MOCK: depois vem do backend (contagem por prioridade + lista de casos)
# ------------------------------------------------------------------
URGENCIAS = {
    "U": {"nome": "Urgente", "cor": "#EF4444", "pill": "red"},
    "A": {"nome": "Atenção", "cor": "#EAB308", "pill": "yellow"},
    "R": {"nome": "Rotina", "cor": "#22C55E", "pill": "green"},
}
CONTAGENS = {"U": 12, "A": 18, "R": 34}
CASOS = [
    {"id": "DOC-CLIN-2026-8942", "tipo": "Laudo de imagem", "paciente": "Carlos Eduardo Mendes", "urg": "U"},
    {"id": "DOC-CLIN-2026-8943", "tipo": "Guia", "paciente": "Carlos Eduardo Mendes", "urg": "U"},
    {"id": "DOC-CLIN-2026-8947", "tipo": "Laudo de exame", "paciente": "Renata Silveira", "urg": "A"},
    {"id": "DOC-CLIN-2026-8948", "tipo": "Alta", "paciente": "Marcos Pereira", "urg": "A"},
    {"id": "DOC-4B0278F4", "tipo": "Receituário médico", "paciente": "Talita de Oliveira", "urg": "R"},
    {"id": "DOC-CLIN-2026-8941", "tipo": "Receita", "paciente": "Renata Silveira", "urg": "R"},
    {"id": "DOC-CLIN-2026-8945", "tipo": "Atestado", "paciente": "Carlos Eduardo Mendes", "urg": "R"},
    {"id": "DOC-CLIN-2026-8940", "tipo": "Laudo de imagem", "paciente": "Carlos Eduardo Mendes", "urg": "U"},
]
POR_TELA = 5

ss = st.session_state
filtro = ss.get("filtro_urgencia")  # None, "U", "A" ou "R"


def alternar_filtro(chave: str) -> None:
    ss["filtro_urgencia"] = None if ss.get("filtro_urgencia") == chave else chave


# Destaque do botão selecionado
if filtro:
    st.markdown(
        f"<style>div[class*='st-key-urg_{filtro}'] button "
        f"{{ border: 2px solid {URGENCIAS[filtro]['cor']}; border-left-width: 6px; }}</style>",
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------------
# CABEÇALHO E BOTÕES DE URGÊNCIA
# ------------------------------------------------------------------
st.title("Home")
st.caption("Visão geral dos casos em triagem. Clique em uma urgência para filtrar a lista.")

for coluna, (chave, u) in zip(st.columns(3, gap="medium"), URGENCIAS.items()):
    with coluna:
        st.button(
            f"{u['nome']}\n\n{CONTAGENS[chave]}",
            key=f"urg_{chave}",
            on_click=alternar_filtro,
            args=(chave,),
            use_container_width=True,
        )

st.write("")
col_graf, col_lista = st.columns([5, 7], gap="large")

# ------------------------------------------------------------------
# GRÁFICO DE BARRAS
# ------------------------------------------------------------------
with col_graf:
    with st.container(key="card_grafico"):
        maximo = max(CONTAGENS.values())
        barras = "".join(
            f'<div class="barra-col"><b>{CONTAGENS[k]}</b>'
            f'<div style="height:{round(CONTAGENS[k] / maximo * 120)}px;background:{u["cor"]}"></div></div>'
            for k, u in URGENCIAS.items()
        )
        rotulos = "".join(f"<span>{u['nome']}</span>" for u in URGENCIAS.values())
        st.markdown(
            '<p class="card-title" style="font-weight:700;margin:0 0 12px">CASOS POR URGÊNCIA</p>'
            f'<div class="barras">{barras}</div>'
            f'<div class="barras-rotulos">{rotulos}</div>'
            f'<p style="font-size:.8rem;opacity:.7;margin-top:10px">'
            f"Total: <b>{sum(CONTAGENS.values())}</b> casos em aberto</p>",
            unsafe_allow_html=True,
        )

# ------------------------------------------------------------------
# LISTA DE CASOS (cada linha abre o Dashboard)
# ------------------------------------------------------------------
with col_lista:
    with st.container(key="card_casos"):
        titulo = f"CASOS: {URGENCIAS[filtro]['nome'].upper()}" if filtro else "CASOS RECENTES"
        c_tit, c_limpar = st.columns([3, 1], vertical_alignment="center")
        c_tit.markdown(f'<p style="font-weight:700;margin:0">{titulo}</p>', unsafe_allow_html=True)
        if filtro:
            c_limpar.button("Limpar filtro", on_click=alternar_filtro, args=(filtro,), key="limpar")

        visiveis = [c for c in CASOS if not filtro or c["urg"] == filtro][:POR_TELA]
        largura = [3, 2.5, 3, 1.5, 1.3]

        cab = st.columns(largura)
        for col, texto in zip(cab, ["ID", "Tipo", "Paciente", "Urgência", ""]):
            col.markdown(f"<span style='font-size:.8rem;opacity:.7'>{texto}</span>", unsafe_allow_html=True)

        for caso in visiveis:
            c1, c2, c3, c4, c5 = st.columns(largura, vertical_alignment="center")
            u = URGENCIAS[caso["urg"]]
            c1.markdown(f"<span style='font-size:.85rem'>{caso['id']}</span>", unsafe_allow_html=True)
            c2.markdown(f"<span style='font-size:.85rem'>{caso['tipo']}</span>", unsafe_allow_html=True)
            c3.markdown(f"<span style='font-size:.85rem'>{caso['paciente']}</span>", unsafe_allow_html=True)
            c4.markdown(pill(u["nome"], u["pill"]), unsafe_allow_html=True)
            if c5.button("Abrir", key=f"abrir_{caso['id']}", icon=":material/arrow_forward:"):
                ss["ultimo_documento_id"] = caso["id"]
                st.switch_page(PAGINA_DASHBOARD)

        total_filtro = CONTAGENS[filtro] if filtro else sum(CONTAGENS.values())
        rodape, link = st.columns([1, 1], vertical_alignment="center")
        rodape.caption(f"Mostrando {len(visiveis)} de {total_filtro}")
        with link:
            st.page_link(PAGINA_LISTA, label="Ver todos em Documentos", icon=":material/arrow_forward:")

