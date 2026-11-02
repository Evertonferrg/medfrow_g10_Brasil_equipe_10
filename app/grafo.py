import logging
from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import config
from . import roteamento as rt
from .alerta import gerar_alerta                                  # NOVO (H3.3.1)
from .arquivos import extensao_por_assinatura
from .llm import extrair, ler_imagem
from .modelos import Classificacao, Destino
from .modelos.destino import DecisaoRoteamento, Notificacao
from .pdf import PDFSemTexto, extrair_texto_pdf, renderizar_paginas
from .resposta import falha_de_processamento, montar_resposta
from .schemas import Extracao
from .urgencia import avaliar_urgencia, carregar_regras          # NOVO (H3.1)
from .validacao import validar

logger = logging.getLogger(__name__)


# Dicionário compartilhado entre os nós do LangGraph
class Estado(TypedDict, total=False):
    documento_id: str
    texto: str
    pdf_bytes: bytes | None  # na prática: bytes do arquivo (PDF, PNG ou JPG)
    limite_confianca: float  # H1.2.2 T2: carregado uma vez por execução do grafo
    extracao: Extracao | None  # objeto Extracao (None se falhou)
    classificacao: (
        Classificacao | None
    )  # objeto Classificacao montado pelo nó classificar
    erro: str | None
    problemas: list
    score: float
    destino: Destino
    regra: str  # id da regra aplicada (R-URGENCIA, R-RECEITA...)
    requer_revisao: bool
    motivo_revisao: str | None
    justificativa: str
    notificacao: Notificacao | None
    tipo_arquivo: str  # "TEXTO", "PDF" ou "Imagem"
    ilegivel: bool
    resultado: dict
    decisao_roteamento: (
        DecisaoRoteamento | None
    )  # submodelo DecisaoRoteamento (H2.1.1 T1/T4)
    canal_origem: str | None   # NOVO H3.1.2: vem da rota de envio
    nivel_prioridade: str      # NOVO H3.1.3: Urgente | Prioritário | Rotina (sempre gravado)
    sinal_prioridade: str      # NOVO H3.1.3: o que definiu o nível
    achado_critico: str | None # NOVO


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


def _valor(x):                                                    # NOVO
    return x.value if hasattr(x, "value") else x


def _com_nivel(extracao, nivel: str):                             # NOVO
    """Cópia da extração com o nível final (sem revalidar o campo)."""
    if extracao is None or _valor(getattr(extracao, "nivel_prioridade", None)) == nivel:
        return extracao
    try:
        return extracao.model_copy(update={"nivel_prioridade": nivel})
    except AttributeError:
        extracao.nivel_prioridade = nivel
        return extracao


def construir_grafo(
    extrator=extrair, classificador=montar_classificacao, leitor=None, confirmador=None  # NOVO: confirmador
):
    """'extrator', 'classificador', 'leitor' e 'confirmador' podem ser trocados por
    versões falsas nos testes (sem LLM, sem rede)."""
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

    def n_avaliar_urgencia(s: Estado):                            # NOVO NÓ (H3.1.1/2/3)
        """SEMPRE roda antes de decidir (também com erro, score baixo ou ilegível).
        Só grava nível/sinal/achado; quem escolhe o destino é o nó decidir."""
        e = s.get("extracao")
        aval = avaliar_urgencia(
            s.get("texto", ""),
            s.get("canal_origem"),
            _valor(getattr(e, "nivel_prioridade", None)) if e is not None else None,
            carregar_regras(config.ARQUIVO_REGRAS),
            confirmador,
        )
        nivel = _valor(aval.nivel)
        return {
            "nivel_prioridade": nivel,
            "sinal_prioridade": aval.sinal,
            "achado_critico": aval.achado,
            "extracao": _com_nivel(e, nivel),
        }

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
        limite = (
            s["limite_confianca"]
            if "limite_confianca" in s
            else config.limite_confianca()
        )
        decisao = rt.criar_decisao_roteamento(s, limite_confianca=limite)
        return {
            "destino": str(decisao.destino_principal),
            "regra": decisao.regra_aplicada,
            "requer_revisao": decisao.requer_auditoria_humana,
            "justificativa": decisao.justificativa_roteamento,
            "notificacao": decisao.notificacao_gerada.model_dump()
            if decisao.notificacao_gerada
            else None,
            "decisao_roteamento": decisao,
        }

    def n_rotear(s: Estado):
        """H2.1.1 T4: grava a decisão no estado e no resultado.
        No MVP, a fila de um setor é a consulta aos resultados com aquele destino."""
        decisao = s.get("decisao_roteamento")
        if decisao is not None:
            return {
                "destino": str(decisao.destino_principal),
                "regra": decisao.regra_aplicada,
                "requer_revisao": decisao.requer_auditoria_humana,
                "motivo_revisao": s.get("motivo_revisao")
                if decisao.requer_auditoria_humana
                else None,
                "justificativa": decisao.justificativa_roteamento,
                "notificacao": (
                    decisao.notificacao_gerada.model_dump()
                    if decisao.notificacao_gerada
                    else None
                ),
            }

    def n_alertar_plantao(s: Estado):                             # NOVO NÓ (H3.3.1 T2)
        """Só roda para Urgente roteado (sem revisão). Mensagem por modelo de texto,
        até 200 caracteres; grava no estado e na decisão de roteamento."""
        e = s.get("extracao")
        achado = (
            s.get("achado_critico")
            or getattr(e, "diagnostico_principal", None)
            or getattr(e, "tipo_documento", None)
        )
        nome = getattr(getattr(e, "paciente", None), "nome", None)
        alerta = gerar_alerta(achado, nome, s.get("canal_origem"))
        saida = {"notificacao": alerta.model_dump()}
        decisao = s.get("decisao_roteamento")
        if decisao is not None:
            saida["decisao_roteamento"] = decisao.model_copy(
                update={"notificacao_gerada": alerta}
            )
        return saida

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
            resultado = falha_de_processamento(doc_id, str(e))
            return {
                "destino": str(Destino.FILA_REVISAO_HUMANA),
                "regra": "R-REVISAO",
                "requer_revisao": True,
                "motivo_revisao": "falha de processamento",
                "classificacao": None,
                "notificacao": None,
                "justificativa": resultado.decisao_roteamento.justificativa_roteamento,
                "resultado": resultado.model_dump(mode="json"),
            }

    def urgente_roteado(s: Estado) -> str:                        # NOVO (condicional)
        """Alerta só para urgência decidida (a dúvida já notifica pelo próprio roteamento)."""
        if s.get("regra") == "R-URGENCIA" and not s.get("requer_revisao"):
            return "alertar_plantao"
        return "montar_resultado"

    g = StateGraph(Estado)
    for nome, fn in [
        ("ler_entrada", n_ler_entrada),
        ("extrair", n_extrair),
        ("validar", n_validar),
        ("avaliar_urgencia", n_avaliar_urgencia),                 # NOVO
        ("classificar", n_classificar),
        ("decidir", n_decidir),
        ("rotear", n_rotear),
        ("alertar_plantao", n_alertar_plantao),                   # NOVO
        ("montar_resultado", n_montar_resultado),
    ]:
        g.add_node(nome, fn)

    g.set_entry_point("ler_entrada")
    # T5: ilegível pula extrair/validar/classificar, mas NÃO pula a urgência (H3.1.2 T3)
    g.add_conditional_edges(
        "ler_entrada",
        lambda s: "avaliar_urgencia" if s.get("ilegivel") else "extrair",   # NOVO destino
        {"avaliar_urgencia": "avaliar_urgencia", "extrair": "extrair"},
    )
    g.add_edge("extrair", "validar")
    g.add_edge("validar", "avaliar_urgencia")                     # NOVO (antes: validar → classificar)
    g.add_conditional_edges(                                      # NOVO
        "avaliar_urgencia",
        lambda s: "decidir" if s.get("ilegivel") else "classificar",
        {"decidir": "decidir", "classificar": "classificar"},
    )
    g.add_edge("classificar", "decidir")
    g.add_edge("decidir", "rotear")
    g.add_conditional_edges(                                      # NOVO (antes: rotear → montar_resultado)
        "rotear",
        urgente_roteado,
        {"alertar_plantao": "alertar_plantao", "montar_resultado": "montar_resultado"},
    )
    g.add_edge("alertar_plantao", "montar_resultado")             # NOVO
    g.add_edge("montar_resultado", END)
    return g.compile()


def triar(
    texto: str,
    extrator=extrair,
    pdf_bytes: bytes | None = None,
    classificador=montar_classificacao,
    leitor=None,
    documento_id: str = "",
    canal_origem: str | None = None,                              # NOVO
    confirmador=None,                                             # NOVO
) -> dict:
    return construir_grafo(extrator, classificador, leitor, confirmador).invoke(
        {
            "texto": texto,
            "pdf_bytes": pdf_bytes,
            "documento_id": documento_id,
            "canal_origem": canal_origem,                         # NOVO
        }
    )