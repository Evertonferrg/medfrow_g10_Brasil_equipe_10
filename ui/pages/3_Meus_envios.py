import os

import pandas as pd
import requests
import streamlit as st

from ui.componentes.resultado import mostrar_resultado

API = os.getenv("API_URL", "http://localhost:8000")
CANAIS = ["Todos", "Pronto_Socorro", "Ambulatorio", "Laboratorio", "Operadora"]

st.title("📋 Meus envios")
canal = st.selectbox("Canal de origem", CANAIS)

try:
    r = requests.get(
        f"{API}/documentos",
        params={} if canal == "Todos" else {"canal_origem": canal},
        timeout=30,
    )
    r.raise_for_status()
except requests.RequestException as e:
    st.error(f"Não consegui falar com a API: {e}")
    st.stop()

itens = r.json()
if not itens:
    st.info("Nenhum documento enviado ainda.")
    st.stop()

df = pd.DataFrame(itens)[
    ["data", "documento_id", "tipo_documento", "nivel_prioridade", "destino", "status", "motivo_rejeicao"]
]
df.columns = ["Data", "Documento", "Tipo", "Prioridade", "Destino", "Status", "Motivo de rejeição"]

evento = st.dataframe(
    df,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

linhas = evento.selection.rows
if linhas:
    doc_id = df.iloc[linhas[0]]["Documento"]
    st.divider()
    st.subheader(f"Detalhe: {doc_id}")
    det = requests.get(f"{API}/documentos/{doc_id}", timeout=30)
    if det.status_code == 200:
        mostrar_resultado(det.json())
    else:
        st.error(det.json().get("detail", det.text))