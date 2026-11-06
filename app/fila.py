"""H4.2.2 T1 — ordenação da fila de revisão (função pura, fácil de testar).

Não depende de H3.1.3: aceita a prioridade como texto ou como enum (usa .value).
Se o projeto tiver `ordem_prioridade` em app.schemas, ela é usada; senão vale a
ordem local abaixo (mais urgente primeiro).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

try:  # H3.1.3, quando existir
    from app.schemas import ordem_prioridade as _ordem_do_projeto
except ImportError:
    _ordem_do_projeto = None

_ORDEM_LOCAL = {"urgente": 0, "prioritario": 1, "rotina": 2}


def _normalizar(valor) -> str:
    texto = str(getattr(valor, "value", valor))
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


def ordem_da_prioridade(prioridade) -> int:
    if _ordem_do_projeto is not None:
        return _ordem_do_projeto(prioridade)
    return _ORDEM_LOCAL.get(
        _normalizar(prioridade), len(_ORDEM_LOCAL)
    )  # desconhecida: por último


@dataclass
class CasoRevisao:
    documento_id: str
    tipo: str
    motivos: list[str]
    chegada_em: datetime
    prioridade: object  # texto ("Prioritário", "Rotina") ou enum NivelPrioridade
    destaques_dose: list[dict] = field(default_factory=list)  # [{'medicamento','dose'}]


def ordenar_fila(casos: list[CasoRevisao]) -> list[CasoRevisao]:
    """Prioridade clínica primeiro; em empate, o mais antigo primeiro."""
    return sorted(
        casos, key=lambda c: (ordem_da_prioridade(c.prioridade), c.chegada_em)
    )
