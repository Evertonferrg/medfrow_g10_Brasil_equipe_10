from pydantic import ValidationError

from .modelos import TipoDocumento
from .modelos.validados import GuiaValidada, ReceitaValidada

MODELOS = {
    TipoDocumento.RECEITUARIO_MEDICO.value: ReceitaValidada,
    TipoDocumento.GUIA_PROCEDIMENTO.value: GuiaValidada,
}

# Chaves que só existem no formato plano (testes unitários).
# "medico_solicitante" fica de fora: no dado real ele é um dicionário.
CAMPOS_PLANOS = {"nome_paciente", "medicamento", "dose", "crm", "procedimento"}


def _get(d, *chaves):
    for c in chaves:
        if not isinstance(d, dict):
            return None
        d = d.get(c)
    return d


def _achatar(tipo: str, dados: dict) -> dict:
    """Converte a Extracao aninhada nos campos planos do modelo validado.
    Se o dado já vier plano (como nos testes unitários), mantém."""
    if CAMPOS_PLANOS & dados.keys():
        return dados

    medico = dados.get("medico_solicitante")
    saida = {
        "nome_paciente": _get(dados, "paciente", "nome"),
        "crm": _get(dados, "medico_solicitante", "crm"),
    }
    if tipo == TipoDocumento.RECEITUARIO_MEDICO.value:
        meds = dados.get("medicamentos") or []
        primeiro = meds[0] if meds else {}
        saida["medicamento"] = _get(primeiro, "nome")
        saida["dose"] = _get(primeiro, "dose")
    else:
        exames = dados.get("exames") or []
        primeiro = exames[0] if exames else {}
        saida["procedimento"] = _get(primeiro, "nome")
        saida["medico_solicitante"] = (
            medico.get("nome") if isinstance(medico, dict) else medico
        )
    return saida


def campos_faltantes(tipo, dados: dict) -> list[str]:
    modelo = MODELOS.get(str(tipo))
    if modelo is None:
        return []
    try:
        modelo.model_validate(_achatar(str(tipo), dados))
    except ValidationError as e:
        return [f"campo faltante: {err['loc'][0]}" for err in e.errors()]
    return []
