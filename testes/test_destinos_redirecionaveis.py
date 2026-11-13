"""Roda no repositório: a lista de destinos aceitos na decisão acompanha o enum Destino."""

from app.modelos import Destino
from app.revisao import DESTINOS_REDIRECIONAVEIS


def test_redirecionaveis_sao_todos_os_destinos_menos_a_revisao():
    todos = {d.value for d in Destino}
    assert DESTINOS_REDIRECIONAVEIS == todos - {Destino.FILA_REVISAO_HUMANA.value}
