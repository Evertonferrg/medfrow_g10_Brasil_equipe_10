# Página inicial. Rodar (na raiz do projeto): streamlit run ui/Home.py
import streamlit as st

st.set_page_config(page_title="MediFlow", page_icon="🏥", layout="wide")
st.title("🏥 MediFlow")
st.write("Triagem inteligente de documentos clínicos. Escolha uma página no menu lateral.")
