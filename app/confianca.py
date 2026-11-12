"""H4.1.1 — Barrar documentos de baixa confiança.

Módulo responsável por:
  T1. Configurar os campos críticos (em config/regras.json).
  T2. Definir o score global:
      score global = o menor valor entre o score de classificação e a média
      dos scores de campo (score_campos).
  T3. Criar a verificação avaliar_confianca:
      acrescenta um motivo para o score global abaixo do limite e um motivo
      por campo crítico abaixo do limite, citando o campo.
  T4. Nó enviar_revisao grava destino Fila_Revisao_Humana,
      requer_auditoria_humana = true e salva o estado completo em
      auditoria_humana/<id>.json para retomada (H5.1.3).
"""

from __future__ import annotations

import logging
from typing import Any

from . import config
from .schemas import Extracao

logger = logging.getLogger(__name__)


def _obter_valor_aninhado(dado: Any, caminho: str) -> Any:
    """Acessa propriedades ou dicionários usando notação com ponto (ex: 'paciente.nome')."""
    partes = caminho.split(".")
    atual = dado
    for parte in partes:
        if atual is None:
            return None
        if isinstance(atual, dict):
            atual = atual.get(parte)
        elif hasattr(atual, parte):
            atual = getattr(atual, parte)
        else:
            return None
    return atual


def _extrair_score_ou_presenca(valor: Any) -> float:
    """Extrai confiança de um campo:
    - Se for numérico (float/int), retorna o próprio valor clamped entre 0.0 e 1.0.
    - Se for booleano, 1.0 para True, 0.0 para False.
    - Se for string/objeto presente e não vazio, 1.0.
    - Se for None ou vazio, 0.0.
    """
    if valor is None:
        return 0.0
    if isinstance(valor, bool):
        return 1.0 if valor else 0.0
    if isinstance(valor, (int, float)):
        return max(0.0, min(1.0, float(valor)))
    if isinstance(valor, str):
        return 1.0 if valor.strip() else 0.0
    if isinstance(valor, (list, tuple, set, dict)):
        return 1.0 if len(valor) > 0 else 0.0
    return 1.0


def obter_scores_campos(extracao: Extracao | dict[str, Any] | None) -> dict[str, float]:
    """Extrai ou calcula os scores de cada campo da extração (H1.3.6 / H4.1.1).

    Verifica explicitamente se há atributo/dicionário score_campos.
    Caso não exista mapa explícito de scores, calcula a confiança dos campos
    com base nas evidências/valores extraídos.
    """
    if extracao is None:
        return {}

    # Se já existir um mapa de score_campos direto no objeto/dict
    score_campos_existente = None
    if isinstance(extracao, dict):
        score_campos_existente = extracao.get("score_campos")
    elif hasattr(extracao, "score_campos"):
        score_campos_existente = getattr(extracao, "score_campos")

    if isinstance(score_campos_existente, dict):
        return {str(k): float(v) for k, v in score_campos_existente.items()}

    scores: dict[str, float] = {}

    # Extrai valores para os campos conhecidos
    # 1. paciente.nome
    p_nome = _obter_valor_aninhado(extracao, "paciente.nome")
    scores["paciente.nome"] = _extrair_score_ou_presenca(p_nome)

    # 2. medico_solicitante.crm
    m_crm = _obter_valor_aninhado(extracao, "medico_solicitante.crm")
    scores["medico_solicitante.crm"] = _extrair_score_ou_presenca(m_crm)

    # 3 e 4. medicamentos.nome e medicamentos.dose
    meds = _obter_valor_aninhado(extracao, "medicamentos")
    if isinstance(meds, list) and len(meds) > 0:
        scores_nome = []
        scores_dose = []
        for m in meds:
            nome = _obter_valor_aninhado(m, "nome")
            dose = _obter_valor_aninhado(m, "dose")
            scores_nome.append(_extrair_score_ou_presenca(nome))
            scores_dose.append(_extrair_score_ou_presenca(dose))
        scores["medicamentos.nome"] = sum(scores_nome) / len(scores_nome) if scores_nome else 0.0
        scores["medicamentos.dose"] = sum(scores_dose) / len(scores_dose) if scores_dose else 0.0

    # 5. cid_sugerido
    cid = _obter_valor_aninhado(extracao, "cid_sugerido") or _obter_valor_aninhado(extracao, "cid")
    if cid is not None:
        scores["cid_sugerido"] = _extrair_score_ou_presenca(cid)

    return scores


def calcular_score_global(
    score_classificacao: float,
    scores_campos: dict[str, float] | None,
) -> float:
    """T2: score global = o menor valor entre o score de classificação e a média dos scores de campo."""
    score_cls = max(0.0, min(1.0, float(score_classificacao)))
    if not scores_campos:
        return score_cls

    valores = list(scores_campos.values())
    if not valores:
        return score_cls

    media_campos = sum(valores) / len(valores)
    return round(min(score_cls, media_campos), 4)


def avaliar_confianca(
    score_classificacao: float,
    extracao: Extracao | dict[str, Any] | None,
    limite: float | None = None,
    scores_campos: dict[str, float] | None = None,
) -> tuple[float, list[str], bool]:
    """T3: Verificação de confiança.

    Acrescenta um motivo para o score global abaixo do limite e um motivo por
    campo crítico abaixo do limite, citando o campo.

    Retorna:
      (score_global, motivos, requer_revisao)
    """
    if limite is None:
        limite = config.limite_confianca()

    if scores_campos is None:
        scores_campos = obter_scores_campos(extracao)

    score_glob = calcular_score_global(score_classificacao, scores_campos)
    motivos: list[str] = []

    # Motivo para score global abaixo do limite
    if score_glob < limite:
        motivos.append(f"score global abaixo do limite ({score_glob:.2f} < {limite:.2f})")

    # Motivos por campo crítico abaixo do limite
    campos_criticos_config = config.campos_criticos()
    for campo in campos_criticos_config:
        if campo in scores_campos:
            val_campo = scores_campos[campo]
            if val_campo < limite:
                motivos.append(
                    f"confiança baixa no campo crítico '{campo}': {val_campo:.2f} (limite {limite:.2f})"
                )

    requer_revisao = len(motivos) > 0
    return score_glob, motivos, requer_revisao
