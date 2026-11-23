"""Configuração centralizada de timeout HTTP da UI para chamadas à API.

Lê de variáveis de ambiente para permitir ajuste fino em arquiteturas com maior
latência entre regiões (ex.: Ashburn <-> São Paulo) sem alterar o código:
- API_TIMEOUT_CONEXAO_S (padrão: 5.0 segundos)
- API_TIMEOUT_LEITURA_S (padrão: 30.0 segundos)
"""

import os

TIMEOUT_CONEXAO_PADRAO = 5.0
TIMEOUT_LEITURA_PADRAO = 30.0


def _ler_float_positivo(nome_env: str, padrao: float) -> float:
    bruto = os.getenv(nome_env)
    if bruto is None:
        return padrao
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        return padrao
    return valor if valor > 0 else padrao


def timeout_api(leitura_minima: float | None = None) -> tuple[float, float]:
    """Devolve (timeout_conexao, timeout_leitura) em segundos para `requests`."""
    conexao = _ler_float_positivo("API_TIMEOUT_CONEXAO_S", TIMEOUT_CONEXAO_PADRAO)
    leitura = _ler_float_positivo("API_TIMEOUT_LEITURA_S", TIMEOUT_LEITURA_PADRAO)
    if leitura_minima is not None and leitura < leitura_minima:
        leitura = leitura_minima
    return (conexao, leitura)
