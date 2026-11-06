"""H4.1.4 — verificação de prescrições de alto risco."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

CONFIG_PADRAO = Path(__file__).resolve().parents[2] / "config" / "alta_vigilancia.json"
_DOSE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mcg|µg|mg|g|ml|u\.?i\.?|un)(?![a-z])", re.IGNORECASE)


@dataclass(frozen=True)
class AlertaRisco:
    medicamento: str
    classe: str
    dose: str | None
    fora_da_faixa: bool
    texto: str  # o motivo, em uma frase


def carregar_config(caminho: Path | str | None = None) -> dict:
    return json.loads(Path(caminho or CONFIG_PADRAO).read_text(encoding="utf-8"))


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


def _unidade(u: str) -> str:
    u = u.lower().replace(".", "")
    return "ui" if u in {"ui", "u"} else ("mcg" if u == "µg" else u)


# T3 ---------------------------------------------------------------
def interpretar_dose(texto: str | None) -> tuple[float, str] | None:
    """'500 mg' -> (500.0, 'mg'); '10 UI' -> (10.0, 'ui')."""
    if not texto:
        return None
    m = _DOSE.search(texto)
    if not m:
        return None
    return float(m.group(1).replace(",", ".")), _unidade(m.group(2))


def _dose_fora_da_faixa(dose_texto: str | None, faixa: dict | None) -> bool:
    if not faixa:
        return False
    dose = interpretar_dose(dose_texto)
    if dose is None:
        return False
    valor, unidade = dose
    return unidade != _unidade(faixa["unidade"]) or valor > faixa["max"]


# T4 ---------------------------------------------------------------
def _classe_do(nome_normalizado: str, classes: dict) -> tuple[str, str] | None:
    for classe, principios in classes.items():
        for principio in principios:
            if re.search(rf"\b{re.escape(_normalizar(principio))}\b", nome_normalizado):
                return classe, _normalizar(principio)
    return None


def verificar_alto_risco(
    medicamentos: list[dict], config: dict | None = None
) -> list[AlertaRisco]:
    """`medicamentos`: [{'nome': 'Morfina', 'dose': '500 mg'}, ...]."""
    config = config or carregar_config()
    alertas = []
    for med in medicamentos:
        nome = med.get("nome") or ""
        achado = _classe_do(_normalizar(nome), config["classes"])
        if not achado:
            continue
        classe, principio = achado
        dose_texto = med.get("dose") or med.get("posologia")
        faixa = config.get("faixas_dose", {}).get(principio)
        fora = _dose_fora_da_faixa(dose_texto, faixa)
        if fora:
            texto = (
                f"Alto risco: dose acima da faixa usual ({nome} {dose_texto}; "
                f"máximo configurado {faixa['max']:g} {faixa['unidade']})."
            )
        else:
            texto = (
                f"Alto risco: {nome}" + (f" {dose_texto}" if dose_texto else "") + "."
            )
        alertas.append(AlertaRisco(nome, classe, dose_texto, fora, texto))
    return alertas
