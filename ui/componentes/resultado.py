import streamlit as st


def mostrar_resultado(res: dict) -> None:
    d = res.get("decisao_roteamento") or {}
    st.info(
        f"**Destino: {d.get('destino_principal', '—')}** — "
        f"{d.get('justificativa_roteamento', '')}"
    )

    cl = res.get("classificacao") or {}
    if cl:
        a, b, c = st.columns(3)
        a.metric("Tipo", cl.get("tipo_documento", "—"))
        b.metric("Especialidade", cl.get("especialidade") or "—")
        c.metric("Prioridade", cl.get("nivel_prioridade", "—"))

    dados = res.get("dados_extraidos") or {}
    if dados:
        a, b = st.columns(2)
        a.subheader("Paciente")
        a.json(dados.get("paciente"))
        b.subheader("Médico solicitante")
        b.json(dados.get("medico_solicitante"))
        st.write(
            f"**Diagnóstico** {dados.get('diagnostico_principal') or '-'} "
            f"| **CID:** {dados.get('cid_sugerido') or '-'}"
        )
        if dados.get("medicamentos"):
            st.subheader("Medicamentos")
            st.table(dados["medicamentos"])
        if dados.get("exames"):
            st.subheader("Exames / procedimentos")
            st.table(dados["exames"])

    for p in res.get("problemas") or []:
        st.write(f"- {p}")