"""Urgência e prioridade em três níveis (H3.1.1, H3.1.2, H3.1.3, H6.2.1).

Módulo puro (sem LLM direto, sem Streamlit): recebe o texto, o canal e o nível já indicado na leitura,
e devolve o nível FINAL e o SINAL que o definiu. O LLM entra só por um `confirmador` injetável.

Regra de ouro (H3.1.1): nenhum falso negativo. Na dúvida, fica Urgente.
H6.2.1 T4: ler achados críticos do ServicoRegras a cada execução, sem cópia fixa no código.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class NivelPrioridade(str, Enum):
    ROTINA = "Rotina"
    PRIORITARIO = "Prioritário"
    URGENTE = "Urgente"


_ORDEM = {
    NivelPrioridade.ROTINA: 0,
    NivelPrioridade.PRIORITARIO: 1,
    NivelPrioridade.URGENTE: 2,
}


def ordem(nivel: str | NivelPrioridade) -> int:
    """Rotina < Prioritário < Urgente (H3.1.3 T1). Levanta ValueError se o nível não existe."""
    return _ORDEM[NivelPrioridade(nivel)]


def maximo(*niveis: str | NivelPrioridade) -> NivelPrioridade:
    """Maior nível da lista: elevar nunca rebaixa um Urgente (H3.1.2 T2)."""
    return max((NivelPrioridade(n) for n in niveis), key=ordem)


def _char(c: str) -> str:
    base = (
        "".join(
            x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x)
        )
        or c
    )
    r = base.lower()
    return (
        r if len(r) == 1 else c
    )  # garante 1 caractere -> os índices batem com o texto original


def normalizar(texto: str) -> str:
    """Sem acento e sem caixa, com o MESMO comprimento do texto (para localizar o trecho)."""
    return "".join(_char(c) for c in texto)


def _padrao(termo: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<!\w){re.escape(normalizar(termo).strip())}(?!\w)"
    )  # palavra inteira


@dataclass(frozen=True)
class Candidato:
    achado: str
    termo: str
    inicio: int
    fim: int
    trecho: str


@dataclass
class Avaliacao:
    nivel: NivelPrioridade
    sinal: str  # ex.: "achado crítico: TEP", "canal Pronto_Socorro", "nenhum sinal"
    achado: str | None = None
    trecho: str | None = None
    motivos_revisao: list = field(default_factory=list)


def buscar_candidatos(
    texto: str, achados_criticos: dict[str, list[str]] | list
) -> list[Candidato]:
    """H3.1.1 T2: cada ocorrência de um achado (ou sinônimo) vira candidata, com o trecho."""
    norm = normalizar(texto)
    candidatos: list[Candidato] = []

    dicionario: dict[str, list[str]] = {}
    if isinstance(achados_criticos, dict):
        dicionario = achados_criticos
    elif isinstance(achados_criticos, list):
        for item in achados_criticos:
            nome = getattr(item, "nome", None) or (
                item.get("nome") if isinstance(item, dict) else None
            )
            sin = (
                getattr(item, "sinonimos", None)
                or (item.get("sinonimos") if isinstance(item, dict) else None)
                or []
            )
            if nome:
                dicionario[nome] = list(sin)

    for achado, sinonimos in dicionario.items():
        # Assegura que o próprio nome do achado seja testado caso a lista de sinônimos esteja vazia
        termos = list(sinonimos) if sinonimos else [achado]
        if achado not in termos:
            termos.append(achado)

        for termo in termos:
            if not str(termo).strip():
                continue
            for m in _padrao(termo).finditer(norm):
                trecho = (
                    texto[max(0, m.start() - 70) : m.end() + 70]
                    .replace("\n", " ")
                    .strip()
                )
                candidatos.append(Candidato(achado, termo, m.start(), m.end(), trecho))
    return sorted(candidatos, key=lambda c: c.inicio)


PROMPT_CONFIRMACAO = """Você revisa laudos médicos. Abaixo estão o texto e uma lista numerada de TRECHOS
onde aparece um termo de achado crítico. Para cada item diga se o achado é:
- "afirmado": o paciente tem o achado;
- "suspeito": há suspeita, hipótese ou 'a esclarecer';
- "negado": o texto NEGA de forma EXPLÍCITA (ex.: "ausência de sinais de TEP", "sem evidência de AVC").
Para "negado", copie em "trecho_negacao" a frase EXATA do texto que nega. Na dúvida, NÃO use "negado".
Liste também em "outros_achados" qualquer achado crítico (TEP, IAM, AVC, sepse, dissecção de aorta,
hemorragia intracraniana) escrito de outra forma e que não esteja na lista.
Responda SOMENTE com JSON: {"candidatos":[{"i":0,"estado":"afirmado|suspeito|negado","trecho_negacao":""}],
"outros_achados":[]}.

TEXTO:
{texto}

TRECHOS:
{trechos}
"""


def montar_prompt(texto: str, candidatos: list) -> str:
    trechos = (
        "\n".join(
            f'{i}. [{c.achado}] "...{c.trecho}..."' for i, c in enumerate(candidatos)
        )
        or "(nenhum)"
    )
    return PROMPT_CONFIRMACAO.replace("{texto}", texto).replace("{trechos}", trechos)


def _aplicar_confirmacao(texto: str, candidatos: list, resposta: dict):
    """Só rebaixa um candidato com negação explícita E um trecho que existe de verdade no texto,
    perto do candidato (anti-alucinação). Qualquer outra coisa mantém o candidato.
    """
    norm = normalizar(texto)
    negados = set()
    for item in (resposta or {}).get("candidatos", []):
        i = item.get("i")
        cit = normalizar(str(item.get("trecho_negacao") or "")).strip()
        if item.get("estado") != "negado" or not cit or not isinstance(i, int):
            continue
        if not (0 <= i < len(candidatos)):
            continue
        pos = norm.find(cit)
        if pos >= 0 and abs(pos - candidatos[i].inicio) <= 200:
            negados.add(i)
    restantes = [c for i, c in enumerate(candidatos) if i not in negados]
    outros = [
        str(x).strip()
        for x in (resposta or {}).get("outros_achados", [])
        if str(x).strip()
    ]
    return restantes, outros


Confirmador = Callable[[str, list], dict]


def obter_achados_criticos_servico() -> dict[str, list[str]]:
    """H6.2.1 T4: Busca a lista de achados críticos no ServicoRegras a cada execução."""
    try:
        from app.regras import servico_regras

        cfg = servico_regras().obter_regras()
        resultado = {}
        for a in cfg.achados_criticos:
            nome = getattr(a, "nome", None) or (
                a.get("nome") if isinstance(a, dict) else None
            )
            sin = (
                getattr(a, "sinonimos", None)
                or (a.get("sinonimos") if isinstance(a, dict) else None)
                or []
            )
            if nome:
                resultado[nome] = list(sin)
        if resultado:
            return resultado
    except Exception:
        logger.exception("Falha ao obter achados do ServicoRegras")

    return {
        "TEP": ["TEP", "tromboembolismo pulmonar", "embolia pulmonar"],
        "IAM": ["IAM", "infarto agudo do miocárdio", "infarto do miocárdio"],
        "AVC": [
            "AVC",
            "AVCI",
            "AVCH",
            "acidente vascular cerebral",
            "acidente vascular encefálico",
        ],
        "Sepse": ["sepse", "choque séptico", "sepsis"],
        "Dissecção de aorta": [
            "dissecção de aorta",
            "dissecção aórtica",
            "dissecção aguda de aorta",
        ],
        "Hemorragia intracraniana": [
            "hemorragia intracraniana",
            "hemorragia intracerebral",
            "hemorragia subaracnóidea",
            "hematoma intracraniano",
        ],
    }


def avaliar_urgencia(
    texto: str,
    canal: str | None = None,
    nivel_atual: str | NivelPrioridade | None = None,
    regras: dict | None = None,
    confirmador: Confirmador | None = None,
) -> Avaliacao:
    """Sempre devolve exatamente UM nível e o sinal que o definiu (H3.1.3 T2/T3).

    nivel_atual: o que a leitura do documento já indicou (hoje vem do LLM da extração).
    H6.2.1 T4: busca a lista no ServicoRegras a cada execução caso regras não seja informado
    ou não contenha achados_criticos explícitos.
    """
    sinais = {n: [] for n in NivelPrioridade}
    motivos, achado, trecho = [], None, None
    texto = texto or ""

    if (
        regras is not None
        and "achados_criticos" in regras
        and regras["achados_criticos"] is not None
    ):
        achados = regras["achados_criticos"]
    else:
        achados = obter_achados_criticos_servico()

    candidatos = buscar_candidatos(texto, achados)
    restantes, outros = list(candidatos), []
    if confirmador is not None:
        try:
            restantes, outros = _aplicar_confirmacao(
                texto, candidatos, confirmador(texto, candidatos)
            )
        except Exception:  # noqa: BLE001
            # LLM fora do ar ou com erro: fica como a regra textual decidiu (anti-falha)
            restantes, outros = list(candidatos), []
            if candidatos:
                motivos.append(
                    "confirmação do LLM indisponível: achado mantido como Urgente"
                )
    if restantes:
        achado, trecho = restantes[0].achado, restantes[0].trecho
        sinais[NivelPrioridade.URGENTE].append(f"achado crítico: {achado}")
    elif outros:
        achado = outros[0]
        sinais[NivelPrioridade.URGENTE].append(
            f"achado crítico: {achado} (apontado na revisão do texto)"
        )

    if nivel_atual is not None:
        atual = NivelPrioridade(nivel_atual)
        if atual != NivelPrioridade.ROTINA:
            sinais[atual].append(
                f"prioridade {atual.value} indicada na leitura do documento"
            )

    norm = normalizar(texto)
    termos_urg = (regras or {}).get(
        "termos_urgencia",
        ["urgente", "urgência", "emergência", "imediato", "CITO"],
    )
    for termo in termos_urg:
        if _padrao(termo).search(norm):
            sinais[NivelPrioridade.PRIORITARIO].append(f'termo "{termo}" no texto')
            break

    canal_norm = normalizar(canal or "")
    canais_prio = (regras or {}).get("canais_prioritarios", ["Pronto_Socorro"])
    for c in canais_prio:
        if canal_norm and normalizar(c) == canal_norm:
            sinais[NivelPrioridade.PRIORITARIO].append(f"canal {c}")
            break

    nivel = maximo(NivelPrioridade.ROTINA, *[n for n, s in sinais.items() if s])
    if sinais[nivel]:
        sinal = "; ".join(sinais[nivel])
    elif candidatos:
        sinal = "nenhum sinal (achado crítico citado apenas com negação explícita)"
    else:
        sinal = "nenhum sinal"
    return Avaliacao(nivel, sinal, achado, trecho, motivos)


REGRAS_PADRAO = {
    "achados_criticos": {
        "TEP": ["TEP", "tromboembolismo pulmonar", "embolia pulmonar"],
        "IAM": ["IAM", "infarto agudo do miocárdio", "infarto do miocárdio"],
        "AVC": [
            "AVC",
            "AVCI",
            "AVCH",
            "acidente vascular cerebral",
            "acidente vascular encefálico",
        ],
        "Sepse": ["sepse", "choque séptico", "sepsis"],
        "Dissecção de aorta": [
            "dissecção de aorta",
            "dissecção aórtica",
            "dissecção aguda de aorta",
        ],
        "Hemorragia intracraniana": [
            "hemorragia intracraniana",
            "hemorragia intracerebral",
            "hemorragia subaracnóidea",
            "hematoma intracraniano",
        ],
    },
    "termos_urgencia": ["urgente", "urgência", "emergência", "imediato", "CITO"],
    "canais_prioritarios": ["Pronto_Socorro"],
}


def carregar_regras(caminho: str | None = None) -> dict:
    """config/regras.json por cima dos padrões: se o arquivo não tiver as chaves, vale o padrão."""
    regras = {
        k: (dict(v) if isinstance(v, dict) else list(v))
        for k, v in REGRAS_PADRAO.items()
    }
    dados = {}
    if caminho:
        try:
            with open(caminho, encoding="utf-8-sig") as f:
                dados = json.loads(f.read())
        except (OSError, ValueError, TypeError):
            dados = {}
    for chave in regras:
        if dados.get(chave):
            regras[chave] = dados[chave]
    return regras


def fazer_confirmador(chamar_llm: Callable[[str], str]) -> Confirmador:
    """Transforma uma função `prompt -> texto` (a chamada ao LLM) no confirmador (H3.1.1 T3).

    Qualquer erro (rede, JSON quebrado) levanta exceção e `avaliar_urgencia` mantém o achado Urgente.
    """

    def confirmador(texto: str, candidatos: list) -> dict:
        bruto = chamar_llm(montar_prompt(texto, candidatos)).strip()
        bruto = re.sub(r"^```(?:json)?|```$", "", bruto, flags=re.MULTILINE).strip()
        return json.loads(bruto)

    return confirmador
