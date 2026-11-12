"""H5.2.2 T4 — Exibir a linha do tempo de um documento no Streamlit."""

from __future__ import annotations

import streamlit as st

ICONES_EVENTO = {
    "recebido": "📥",
    "recebimento": "📥",
    "classificacao": "🏷️",
    "extracao": "📋",
    "decisao": "⚖️",
    "destino": "🚀",
    "processando": "⚙️",
    "processado": "✅",
    "em_auditoria_humana": "🔍",
    "revisao": "🔍",
    "rejeitado": "❌",
}

ROTULOS_TIPO = {
    "recebido": "Recebimento",
    "recebimento": "Recebimento",
    "classificacao": "Classificação",
    "extracao": "Extração de Dados",
    "decisao": "Decisão de Roteamento",
    "destino": "Encaminhamento ao Destino",
    "processando": "Processando",
    "processado": "Processado",
    "em_auditoria_humana": "Encaminhado para Auditoria Humana",
    "revisao": "Revisão Humana",
    "rejeitado": "Rejeitado",
}


def exibir_linha_do_tempo(eventos: list[dict] | None) -> None:
    """Renderiza a lista cronológica com data, hora e evento."""
    if not isinstance(eventos, list) or not eventos:
        return

    itens_validos = [ev for ev in eventos if isinstance(ev, dict)]
    if not itens_validos:
        return

    st.markdown("### ⏱️ Linha do Tempo do Documento")

    for i, ev in enumerate(itens_validos):
        tipo = ev.get("tipo") or ev.get("status") or "evento"
        icone = ICONES_EVENTO.get(str(tipo).lower(), "📌")
        rotulo = ROTULOS_TIPO.get(str(tipo).lower(), str(tipo).capitalize())
        data_hora = ev.get("data_hora") or ev.get("em") or ""
        autor = ev.get("autor") or ev.get("autor_nome") or ev.get("autor_tipo") or "sistema"
        detalhe = ev.get("detalhe")

        with st.container():
            col_icon, col_info = st.columns([1, 15])
            with col_icon:
                st.markdown(f"### {icone}")
            with col_info:
                st.markdown(f"**{rotulo}** &nbsp;•&nbsp; `{data_hora}` &nbsp;•&nbsp; *Autor: {autor}*")
                if detalhe:
                    st.caption(f"{detalhe}")
                extra = ev.get("extra")
                if isinstance(extra, dict) and extra:
                    metas = [f"**{k}:** {v}" for k, v in extra.items() if v is not None]
                    if metas:
                        st.caption(" • ".join(metas))
        if i < len(itens_validos) - 1:
            st.markdown("<div style='border-left: 2px solid #ccc; height: 16px; margin-left: 18px;'></div>", unsafe_allow_html=True)
