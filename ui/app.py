import streamlit as st

pg = st.navigation([
    st.Page("Home.py", title="Home", icon=":material/home:", default=True),
    st.Page("pages/2_Documentos2.py", title="Documentos", icon=":material/folder:"),
    st.Page("pages/novo_documento.py", title="Novo documento", icon=":material/upload_file:"),
    st.Page("pages/2_Triagem.py", title="Triagem", icon=":material/search:"),
    st.Page("pages/3_Dashboard.py", title="Dashboard", icon=":material/dashboard:"),
    st.Page("pages/3_Meus_envios.py", title="Meus envios", icon=":material/list_alt:"),
    st.Page("pages/5_Caso.py", title="Caso", icon=":material/medical_information:"),
    st.Page("pages/6_Fila_revisao.py", title="Fila de revisão", icon=":material/rule:"),
    st.Page("pages/7_Revisao_caso.py", title="Revisão do caso", icon=":material/fact_check:"),
    st.Page("pages/9_Regras.py", title="Regras", icon=":material/tune:"),
])
pg.run()
