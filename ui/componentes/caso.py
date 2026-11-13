"""H3.4.1 T2 — dados do caso para a página de resumo.

O resultado da API traz os campos clínicos dentro de `dados_extraidos`;
aqui eles são juntados com o nível de cima antes de procurar cada campo.
"""

CAMPOS = {
    "paciente": ("paciente", "nome"),
    "origem": ("canal_origem", "origem"),
    "achado": ("diagnostico_principal", "achado_principal", "achado"),
    "cid": ("cid", "cid_sugerido", "cid10"),
    "medico": ("medico_solicitante", "medico"),
}
VAZIO = "—"
NAO_ENCONTRADO = "não encontrado"


def _buscar(dados: dict, chaves: tuple[str, ...]):
    for chave in chaves:
        valor = dados.get(chave)
        if valor in (None, "", [], {}):
            continue
        if isinstance(valor, str) and valor.strip().lower() == NAO_ENCONTRADO:
            continue  # tenta a próxima chave (ex.: cid_sugerido)
        return valor
    return None


def _como_texto(valor) -> str:
    if valor is None:
        return VAZIO
    if isinstance(valor, dict):  # ex.: paciente = {"nome": "...", "idade": 54}
        return valor.get("nome") or VAZIO
    return str(valor)


def dados_do_caso(resultado: dict) -> dict[str, str]:
    """Devolve sempre as 5 chaves de CAMPOS, com '—' quando faltar o dado."""
    extraidos = resultado.get("dados_extraidos")
    dados = {**(extraidos if isinstance(extraidos, dict) else {}), **resultado}
    return {campo: _como_texto(_buscar(dados, chaves)) for campo, chaves in CAMPOS.items()}