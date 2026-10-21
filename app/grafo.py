from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from .llm import extrair
from .pdf import extrair_texto_pdf
from .validacao import validar, precisa_revisao
from . import roteamento as rt


#dicionario comparilhado entre os nos
class Estado(TypedDict, total=False):
    texto: str
    pdf_bytes: Optional[bytes]
    extracao: Optional[object]   # objeto Extracao (None se falhou)
    erro: Optional[str]
    problemas: list
    score: float
    destino: str
    regra: str                   # id da regra aplicada (R-URGENCIA, R-RECEITA...)
    requer_revisao: bool
    justificativa: str
    notificacao: Optional[dict]

def construir_grafo(extrator=extrair):
    """'extrator' pode ser trocado por uma versão falsa nos testes (sem LLM, sem rede)."""

    def n_ler_entrada(s: Estado):
        #estrair textos das paginas
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

    def n_urgencia(s: Estado):
        e = s["extracao"]
        achado = e.diagnostico_principal or e.tipo_documento
        destino, regra = rt.decidir_destino(e.tipo_documento, e.nivel_prioridade, False)
        return {
            "destino": destino, 
            "regra": regra, 
            "requer_revisao": False,
            "justificativa": rt.justificativa(
                e.tipo_documento, e.nivel_prioridade, s["score"], destino, regra, achado=achado
            ),
            "notificacao": {
                "canal": "Alerta_Plantao_Medico",
                "mensagem": f"ALERTA URGENTE: {achado} paciente {e.paciente.nome}."
            }
        }

    def n_revisao(s: Estado):
        e = s.get("extracao")
        destino, regra = rt.decidir_destino("", "", True)
        notificacao = None
        # se parece urgente mas a duvida avisa mesmo assim
        if e is not None and e.nivel_prioridade == "Urgente":
            notificacao = {"canal": "Alerta_Plantao_Medico",
                           "mensagem": "Possivel urgência com dados ambiguos: revisar com prioridade."}
        return {"destino": destino, "regra": regra, "requer_revisao": True, "notificacao": notificacao,
                "justificativa": rt.justificativa("", "", s["score"], destino, regra,
                                                  problemas=s.get("problemas"), erro=s.get("erro"))}

    

    def n_padrao(s: Estado):
        e = s["extracao"]
        destino, regra = rt.decidir_destino(e.tipo_documento, e.nivel_prioridade, False)
        return {"destino": destino, "regra": regra, "requer_revisao": False, "notificacao": None,
                "justificativa": rt.justificativa(e.tipo_documento, e.nivel_prioridade,
                                                  s["score"], destino, regra)}

    # condicional = segurança 1º , depois urgencia , por fim rotina
    def decidir(s: Estado) -> str:
        if s.get("erro") or precisa_revisao(s["score"], s["problemas"]):
            return "revisao"
        return "urgencia" if s["extracao"].nivel_prioridade == "Urgente" else "padrao"

    g = StateGraph(Estado)
    for nome, fn in [("ler_entrada", n_ler_entrada), ("extrair", n_extrair), ("validar", n_validar),
                     ("urgencia", n_urgencia), ("revisao", n_revisao), ("padrao", n_padrao)]:
        g.add_node(nome, fn)
    g.set_entry_point("ler_entrada")
    g.add_edge("ler_entrada", "extrair")
    g.add_edge("extrair", "validar")
    g.add_conditional_edges("validar", decidir,
                            {"urgencia": "urgencia", "revisao": "revisao", "padrao": "padrao"})
    for no in ("urgencia", "revisao", "padrao"):
        g.add_edge(no, END)
    return g.compile()

def triar(texto: str, extrator=extrair, pdf_bytes: Optional[bytes] = None) -> dict:
    return construir_grafo(extrator).invoke({"texto": texto, "pdf_bytes": pdf_bytes})