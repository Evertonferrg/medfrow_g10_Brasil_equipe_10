import logging
from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import config
from . import roteamento as rt
from .arquivos import extensao_por_assinatura
from .llm import extrair, ler_imagem
from .modelos import Classificacao, Destino
from .pdf import PDFSemTexto, extrair_texto_pdf, renderizar_paginas
from .resposta import falha_de_processamento, montar_resposta
from .validacao import motivo_revisao, precisa_revisao, validar
from .roteamento import decidir_destino, criar_decisao_roteamento  # exportado em app/grafo (H2.1.1 T2)

logger = logging.getLogger(__name__)

# Dicionário compartilhado entre os nós do LangGraph
class Estado(TypedDict, total=False):
    documento_id: str
    texto: str
    pdf_bytes: bytes | None  # na prática: bytes do arquivo (PDF, PNG ou JPG)
    limite_confianca: float  # H1.2.2 T2: carregado uma vez por execução do grafo
    extracao: object | None  # objeto Extracao (None se falhou)
    classificacao: object | None  # objeto Classificacao montado pelo nó classificar
    erro: str | None
    problemas: list
    score: float
    destino: str
    regra: str  # id da regra aplicada (R-URGENCIA, R-RECEITA...)
    requer_revisao: bool
    motivo_revisao: str | None
    justificativa: str
    notificacao: dict | None
    tipo_arquivo: str  # "TEXTO", "PDF" ou "Imagem"
    ilegivel: bool
    resultado: dict
    decisao_roteamento: object | None  # submodelo DecisaoRoteamento (H2.1.1 T1/T4)


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
                    return {
                        "texto": extrair_texto_pdf(dados),
                        "tipo_arquivo": "PDF",
                        "limite_confianca": limite,
                    }
                except PDFSemTexto:
                    imagens, tipo = renderizar_paginas(dados), "PDF"  # T2: escaneado
            else:
                imagens, tipo = [dados], "Imagem"
            texto, leg = leitor(imagens)  # T4
        except Exception as e:
            logger.exception("Falha ao ler a entrada")
            return {"texto": "", "erro": str(e), "limite_confianca": limite}

        if not leg.legivel or not texto.strip():  # T5
            motivo = leg.motivo or "sem texto reconhecível"
            return {
                "texto": "",
                "tipo_arquivo": tipo,
                "ilegivel": True,
                "extracao": None,
                "score": 0.0,
                "motivo_revisao": "ilegível",
                "problemas": [f"ilegível: {motivo}"],
                "limite_confianca": limite,
            }
        return {"texto": texto, "tipo_arquivo": tipo, "limite_confianca": limite}

    def n_extrair(s: Estado):
        if s.get("erro"):
            return {"extracao": None}
        try:
            return {"extracao": extrator(s["texto"])}
        except Exception as e:
            logger.exception("Falha na extração automática")
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
            logger.exception("Falha na classificação automática")
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
            "motivo_revisao": None,
            "decisao_roteamento": decisao,
            "justificativa": rt.justificativa(
                e.tipo_documento,
                e.nivel_prioridade,
                s["score"],
                destino,
                regra,
                achado=achado,
            ),
            "notificacao": {
                "canal": "Alerta_Plantao_Medico",
                "mensagem": f"ALERTA URGENTE: {achado} paciente {e.paciente.nome}.",
            },
        }

    def n_revisao(s: Estado):
        e = s.get("extracao")
        limite = (
            s["limite_confianca"]
            if "limite_confianca" in s
            else config.limite_confianca()
        )
        # T5: se a leitura já definiu o motivo (ex.: "ilegível"), respeita; senão calcula
        motivo = s.get("motivo_revisao") or motivo_revisao(
            s.get("score", 0.0), s.get("problemas", []), limite, s.get("erro")
        )
        destino, regra = rt.decidir_destino("", "", True)
        notificacao = None
        # se parece urgente mas a duvida avisa mesmo assim
        if e is not None and e.nivel_prioridade == "Urgente":
            notificacao = {
                "canal": "Alerta_Plantao_Medico",
                "mensagem": "Possivel urgência com dados ambiguos: revisar com prioridade.",
            }
        return {
            "destino": destino,
            "regra": regra,
            "requer_revisao": True,
            "motivo_revisao": motivo,
            "notificacao": notificacao,
            "justificativa": rt.justificativa(
                "",
                "",
                s["score"],
                destino,
                regra,
                problemas=s.get("problemas"),
                erro=s.get("erro"),
                motivo=motivo,
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

    def n_montar_resultado(s: Estado):
        """H2.3.1 T2: último nó. Monta e valida o ResultadoTriagem.

        Se o resultado sair fora do formato (ValidationError), NÃO entrega resposta parcial:
        o documento vai para a revisão com o motivo "falha de processamento".
        """
        doc_id = s.get("documento_id", "")
        try:
            return {"resultado": montar_resposta(doc_id, s).model_dump(mode="json")}
        except Exception as e:
            logger.exception("Resultado fora do formato")
            rev = n_revisao(
                {
                    **s,
                    "erro": f"falha de processamento: {e}",
                    "motivo_revisao": "falha de processamento",
                }
            )
            resultado = falha_de_processamento(
                doc_id,
                str(e),
                justificativa=rev["justificativa"],
                notificacao=rev["notificacao"],
            )
            return {
                **rev,
                "classificacao": None,
                "resultado": resultado.model_dump(mode="json"),
            }

    # condicional = segurança 1º , depois urgencia , por fim rotina
    def decidir(s: Estado) -> str:
        limite = (
            s["limite_confianca"]
            if "limite_confianca" in s
            else config.limite_confianca()
        )
        if s.get("erro") or precisa_revisao(s["score"], s["problemas"], limite):
            return "revisao"
        return "urgencia" if s["extracao"].nivel_prioridade == "Urgente" else "padrao"

    g = StateGraph(Estado)
    for nome, fn in [
        ("ler_entrada", n_ler_entrada),
        ("extrair", n_extrair),
        ("validar", n_validar),
        ("classificar", n_classificar),
        ("decidir", n_decidir),
        ("rotear", n_rotear),
        ("revisao", n_revisao),
        ("padrao", n_padrao),
        ("montar_resultado", n_montar_resultado),
    ]:
        g.add_node(nome, fn)

    g.set_entry_point("ler_entrada")
    # T5: ilegível vai direto para a revisão, sem passar por extrair/validar/classificar
    g.add_conditional_edges(
        "ler_entrada",
        lambda s: "revisao" if s.get("ilegivel") else "extrair",
        {"revisao": "revisao", "extrair": "extrair"},
    )
    g.add_edge("extrair", "validar")
    g.add_edge("validar", "classificar")
    g.add_conditional_edges(
        "classificar",
        decidir,
        {"urgencia": "urgencia", "revisao": "revisao", "padrao": "padrao"},
    )
    for no in ("urgencia", "revisao", "padrao"):
        g.add_edge(no, "montar_resultado")
    g.add_edge("montar_resultado", END)
    return g.compile()


def triar(
    texto: str,
    extrator=extrair,
    pdf_bytes: bytes | None = None,
    classificador=montar_classificacao,
    leitor=None,
    documento_id: str = "",
) -> dict:
    return construir_grafo(extrator, classificador, leitor).invoke(
        {"texto": texto, "pdf_bytes": pdf_bytes, "documento_id": documento_id}
    )
