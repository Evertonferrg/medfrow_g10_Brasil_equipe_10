"""H3.1.3 T4: etiqueta de prioridade reutilizável (cor + texto + emoji, nunca só cor)."""

_ESTILO = {
    "Urgente": ("red", "🔴"),
    "Prioritário": ("orange", "🟠"),
    "Rotina": ("green", "🟢"),
}


def etiqueta_prioridade(nivel) -> str:
    """Markdown do Streamlit: st.markdown(etiqueta_prioridade(nivel))."""
    nome = str(getattr(nivel, "value", nivel) or "")
    cor, emoji = _ESTILO.get(nome, ("gray", "⚪"))
    return f":{cor}-background[{emoji} **{nome or 'Sem prioridade'}**]"
