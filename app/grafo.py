import logging
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from . import config
from .llm import extrair, ler_imagem
from .modelos import Classificacao
from .pdf import extrair_texto_pdf, renderizar_paginas, PDFSemTexto
from .arquivos import extensao_por_assinatura
from .validacao import validar, precisa_revisao, motivo_revisao
from . import roteamento as rt

logger = logging.getLogger(__name__)


# dicionario compartilhado entre os nos
class Estado(TypedDict, total=False):
    texto: str
    pdf_bytes: Optional[bytes]   # na prática: bytes do arquivo (PDF, PNG ou JPG)
    limite_confianca: float      # H1.2.2 T2: carregado uma vez por execução do grafo
    extracao: Optional[object]   # objeto Extracao (None se falhou)
    classificacao: Optional[object]  # objeto Classificacao montado pelo nó classificar
    erro: Optional[str]
    problemas: list
    score: float
    destino: str
    regra: str                   # id da regra aplicada (R-URGENCIA, R-RECEITA...)
    requer_revisao: bool
    motivo_revisao: Optional[str]
    justificativa: str
    notificacao: Optional[dict]
    tipo_arquivo: str            # "TEXTO", "PDF" ou "Imagem"
    ilegivel: bool


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


def construir_grafo(extrator=extrair, classificador=montar_classificacao, leitor=None):
    """'extrator', 'classificador' e 'leitor' podem ser trocados por versões falsas nos
    testes (sem LLM, sem rede)."""
    # Resolvido na chamada (e não na assinatura) para que os testes possam trocar
    # app.grafo.ler_imagem com monkeypatch.
    leitor = leitor or ler_imagem

    def n_ler_entrada(s: Estado):
        # H1.2.2 T2: carrega o limite de confiança uma única vez por execução do grafo
        limite = config.limite_confianca()
        dados = s.get("pdf_bytes")
        if not dados:
            return {"tipo_arquivo": "TEXTO", "limite_confianca": limite}
        try:
            if extensao_por_assinatura(dados) == ".pdf":
                try:
                    return {"texto": extrair_texto_pdf(dados), "tipo_arquivo": "PDF",
                            "limite_confianca": limite}
                except PDFSemTexto:
                    imagens, tipo = renderizar_paginas(dados), "PDF"      # T2: escaneado
            else:
                imagens, tipo = [dados], "Imagem"
            texto, leg = leitor(imagens)                                  # T4
        except Exception as e:
            logger.exception("Falha ao ler a entrada")
            return {"texto": "", "erro": str(e), "limite_confianca": limite}

        if not leg.legivel or not texto.strip():                          # T5
            motivo = leg.motivo or "sem texto reconhecível"
            return {"texto": "", "tipo_arquivo": tipo, "ilegivel": True,
                    "extracao": None, "score": 0.0,
                    "motivo_revisao": "ilegível",
                    "problemas": [f"ilegível: {motivo}"],
                    "limite_confianca": limite}
        return {"texto": texto, "tipo_arquivo": tipo, "limite_confianca": limite}

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
        # T3: grava a classificação no estado; se falhar, segue sem ela
        # (não derruba o fluxo — a resposta entrega classificacao=None).
        if s.get("erro") or s.get("extracao") is None:
            return {"classificacao": None}
        try:
            return {"classificacao": classificador(s["extracao"], s["score"])}
        except Exception:
            return {"classificacao": None}

    def n_urgencia(s: Estado):
        e = s["extracao"]
        achado = e.diagnostico_principal or e.tipo_documento
        destino, regra = rt.decidir_destino(e.tipo_documento, e.nivel_prioridade, False)
        return {
            "destino": destino,
            "regra": regra,
            "requer_revisao": False,
            "motivo_revisao": None,
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
        limite = s["limite_confianca"] if "limite_confianca" in s else config.limite_confianca()
        # T5: se a leitura já definiu o motivo (ex.: "ilegível"), respeita; senão calcula
        motivo = s.get("motivo_revisao") or motivo_revisao(
            s.get("score", 0.0), s.get("problemas", []), limite, s.get("erro")
        )
        destino, regra = rt.decidir_destino("", "", True)
        notificacao = None
        # se parece urgente mas a duvida avisa mesmo assim
        if e is not None and e.nivel_prioridade == "Urgente":
            notificacao = {"canal": "Alerta_Plantao_Medico",
                           "mensagem": "Possivel urgência com dados ambiguos: revisar com prioridade."}
        return {
            "destino": destino,
            "regra": regra,
            "requer_revisao": True,
            "motivo_revisao": motivo,
            "notificacao": notificacao,
            "justificativa": rt.justificativa(
                "", "", s["score"], destino, regra,
                problemas=s.get("problemas"), erro=s.get("erro"), motivo=motivo,
            ),
        }

    def n_padrao(s: Estado):
        e = s["extracao"]
        destino, regra = rt.decidir_destino(e.tipo_documento, e.nivel_prioridade, False)
        return {
            "destino": destino,
            "regra": regra,
            "requer_revisao": False,
            "motivo_revisao": None,
            "notificacao": None,
            "justificativa": rt.justificativa(
                e.tipo_documento, e.nivel_prioridade, s["score"], destino, regra
            ),
        }

    # condicional = segurança 1º , depois urgencia , por fim rotina
    def decidir(s: Estado) -> str:
        limite = s["limite_confianca"] if "limite_confianca" in s else config.limite_confianca()
        if s.get("erro") or precisa_revisao(s["score"], s["problemas"], limite):
            return "revisao"
        return "urgencia" if s["extracao"].nivel_prioridade == "Urgente" else "padrao"

    g = StateGraph(Estado)
    for nome, fn in [("ler_entrada", n_ler_entrada), ("extrair", n_extrair), ("validar", n_validar),
                     ("classificar", n_classificar), ("urgencia", n_urgencia),
                     ("revisao", n_revisao), ("padrao", n_padrao)]:
        g.add_node(nome, fn)
    g.set_entry_point("ler_entrada")
    # T5: ilegível vai direto para a revisão, sem passar por extrair/validar/classificar
    g.add_conditional_edges("ler_entrada",
                            lambda s: "revisao" if s.get("ilegivel") else "extrair",
                            {"revisao": "revisao", "extrair": "extrair"})
    g.add_edge("extrair", "validar")
    g.add_edge("validar", "classificar")
    g.add_conditional_edges("classificar", decidir,
                            {"urgencia": "urgencia", "revisao": "revisao", "padrao": "padrao"})
    for no in ("urgencia", "revisao", "padrao"):
        g.add_edge(no, END)
    return g.compile()


def triar(texto: str, extrator=extrair, pdf_bytes: Optional[bytes] = None,
          classificador=montar_classificacao, leitor=None) -> dict:
    return construir_grafo(extrator, classificador, leitor).invoke(
        {"texto": texto, "pdf_bytes": pdf_bytes})