from typing import Optional, TypedDict
from langgraph.graph import END, StateGraph

from .llm import extrair
from .modelos import Classificacao, Destino
from .pdf import extrair_texto_pdf
from .validacao import validar
from . import roteamento as rt
from .roteamento import decidir_destino, criar_decisao_roteamento  # exportado em app/grafo (H2.1.1 T2)


# Dicionário compartilhado entre os nós do LangGraph
class Estado(TypedDict, total=False):
    texto: str
    pdf_bytes: Optional[bytes]
    extracao: Optional[object]   # objeto Extracao (None se falhou)
    classificacao: Optional[object]  # objeto Classificacao montado pelo nó classificar
    erro: Optional[str]
    problemas: list
    score: float
    destino: str
    regra: str                   # id da regra aplicada (R-URGENCIA, R-RECEITA...)
    requer_revisao: bool
    justificativa: str
    notificacao: Optional[dict]
    decisao_roteamento: Optional[object]  # submodelo DecisaoRoteamento (H2.1.1 T1/T4)


def montar_classificacao(extracao, score) -> Classificacao:
    """T3: a classificação que o analista vê vem da extração JÁ validada.

    O score é o RECALCULADO por app/validacao.py (não o que o LLM deu).
    """
    return Classificacao(
        tipo_documento=extracao.tipo_documento,
        especialidade=extracao.especialidade,
        nivel_prioridade=extracao.nivel_prioridade,
        score_confianca_classificacao=score,
    )


def construir_grafo(extrator=extrair, classificador=montar_classificacao):
    """'extrator' e 'classificador' podem ser trocados por versões falsas nos
    testes (sem LLM, sem rede)."""

    def n_ler_entrada(s: Estado):
        if s.get("pdf_bytes"):
            try:
                return {"texto": extrair_texto_pdf(s["pdf_bytes"])}
            except Exception as e:
                return {"texto": "", "erro": str(e)}
        return {}

    def n_extrair(s: Estado):
        if s.get("erro"):
            return {"extracao": None}
        try:
            return {"extracao": extrator(s["texto"])}
        except Exception as e:
            return {"extracao": None, "erro": f"Falha na extração automática: {e}"}

    def n_validar(s: Estado):
        if s.get("erro"):
            return {"problemas": [], "score": 0.0}
        extracao, problemas, score = validar(s["extracao"], s["texto"])
        return {"extracao": extracao, "problemas": problemas, "score": score}

    def n_classificar(s: Estado):
        if s.get("erro") or s.get("extracao") is None:
            return {"classificacao": None}
        try:
            return {"classificacao": classificador(s["extracao"], s["score"])}
        except Exception:
            return {"classificacao": None}

    def n_decidir(s: Estado):
        """H2.1.1 T3: nó decidir que chama a função pura de roteamento
        aplicando precedência urgência → revisão → tipo.
        """
        decisao = rt.criar_decisao_roteamento(s)
        return {
            "destino": str(decisao.destino_principal),
            "regra": decisao.regra_aplicada,
            "requer_revisao": decisao.requer_auditoria_humana,
            "justificativa": decisao.justificativa_roteamento,
            "notificacao": decisao.notificacao_gerada.model_dump() if decisao.notificacao_gerada else None,
            "decisao_roteamento": decisao,
        }

    def n_rotear(s: Estado):
        """H2.1.1 T4: grava a decisão no estado e no resultado.
        No MVP, a fila de um setor é a consulta aos resultados com aquele destino.
        """
        decisao = s.get("decisao_roteamento") or rt.criar_decisao_roteamento(s)
        return {
            "destino": str(decisao.destino_principal),
            "requer_revisao": False,
            "decisao_roteamento": decisao,
        }

    def n_enviar_revisao(s: Estado):
        """H2.1.1 T3: nó de revisão humana quando auditoria é requerida."""
        decisao = s.get("decisao_roteamento") or rt.criar_decisao_roteamento(s)
        return {
            "destino": Destino.FILA_REVISAO_HUMANA.value,
            "requer_revisao": True,
            "decisao_roteamento": decisao,
        }

    def rota_condicional(s: Estado) -> str:
        """Aresta condicional após decidir: leva a rotear ou a enviar_revisao."""
        if s.get("requer_revisao") or s.get("destino") == Destino.FILA_REVISAO_HUMANA.value:
            return "enviar_revisao"
        return "rotear"

    g = StateGraph(Estado)
    for nome, fn in [
        ("ler_entrada", n_ler_entrada),
        ("extrair", n_extrair),
        ("validar", n_validar),
        ("classificar", n_classificar),
        ("decidir", n_decidir),
        ("rotear", n_rotear),
        ("enviar_revisao", n_enviar_revisao),
    ]:
        g.add_node(nome, fn)

    g.set_entry_point("ler_entrada")
    g.add_edge("ler_entrada", "extrair")
    g.add_edge("extrair", "validar")
    g.add_edge("validar", "classificar")
    g.add_edge("classificar", "decidir")

    g.add_conditional_edges(
        "decidir",
        rota_condicional,
        {"rotear": "rotear", "enviar_revisao": "enviar_revisao"},
    )
    g.add_edge("rotear", END)
    g.add_edge("enviar_revisao", END)

    return g.compile()


def triar(
    texto: str,
    extrator=extrair,
    pdf_bytes: Optional[bytes] = None,
    classificador=montar_classificacao,
) -> dict:
    return construir_grafo(extrator, classificador).invoke(
        {"texto": texto, "pdf_bytes": pdf_bytes}
    )