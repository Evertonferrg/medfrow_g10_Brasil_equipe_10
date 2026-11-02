"""Urgência e prioridade em três níveis (H3.1.1, H3.1.2, H3.1.3).

Módulo puro (sem LLM, sem Streamlit): recebe o texto, o canal e o nível já indicado na leitura,
e devolve o nível FINAL e o SINAL que o definiu. O LLM entra só por um `confirmador` injetável.

Regra de ouro (H3.1.1): nenhum falso negativo. Na dúvida, fica Urgente.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class NivelPrioridade(str, Enum):
    ROTINA = "Rotina"
    PRIORITARIO = "Prioritário"
    URGENTE = "Urgente"


_ORDEM = {NivelPrioridade.ROTINA: 0, NivelPrioridade.PRIORITARIO: 1, NivelPrioridade.URGENTE: 2}


def ordem(nivel) -> int:
    """Rotina < Prioritário < Urgente (H3.1.3 T1). Levanta ValueError se o nível não existe."""
    return _ORDEM[NivelPrioridade(nivel)]


def maximo(*niveis) -> NivelPrioridade:
    """Maior nível da lista: elevar nunca rebaixa um Urgente (H3.1.2 T2)."""
    return max((NivelPrioridade(n) for n in niveis), key=ordem)


def _char(c: str) -> str:
    base = "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x)) or c
    r = base.lower()
    return r if len(r) == 1 else c      # garante 1 caractere -> os índices batem com o texto original


def normalizar(texto: str) -> str:
    """Sem acento e sem caixa, com o MESMO comprimento do texto (para localizar o trecho)."""
    return "".join(_char(c) for c in texto)


def _padrao(termo: str) -> "re.Pattern[str]":
    return re.compile(rf"(?<!\w){re.escape(normalizar(termo).strip())}(?!\w)")   # palavra inteira


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
    sinal: str                       # ex.: "achado crítico: TEP", "canal Pronto_Socorro", "nenhum sinal"
    achado: Optional[str] = None
    trecho: Optional[str] = None
    motivos_revisao: list = field(default_factory=list)


def buscar_candidatos(texto: str, achados_criticos: dict) -> list:
    """H3.1.1 T2: cada ocorrência de um achado (ou sinônimo) vira candidata, com o trecho."""
    norm = normalizar(texto)
    achados = []
    for achado, sinonimos in achados_criticos.items():
        for termo in sinonimos:
            for m in _padrao(termo).finditer(norm):
                trecho = texto[max(0, m.start() - 70): m.end() + 70].replace("\n", " ").strip()
                achados.append(Candidato(achado, termo, m.start(), m.end(), trecho))
    return sorted(achados, key=lambda c: c.inicio)


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
    trechos = "\n".join(f'{i}. [{c.achado}] "...{c.trecho}..."' for i, c in enumerate(candidatos)) or "(nenhum)"
    return PROMPT_CONFIRMACAO.replace("{texto}", texto).replace("{trechos}", trechos)


def _aplicar_confirmacao(texto: str, candidatos: list, resposta: dict):
    """Só rebaixa um candidato com negação explícita E um trecho que existe de verdade no texto,
    perto do candidato (anti-alucinação). Qualquer outra coisa mantém o candidato."""
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
    outros = [str(x).strip() for x in (resposta or {}).get("outros_achados", []) if str(x).strip()]
    return restantes, outros


Confirmador = Callable[[str, list], dict]


def avaliar_urgencia(texto: str, canal: Optional[str], nivel_atual, regras: dict,
                     confirmador: Optional[Confirmador] = None) -> Avaliacao:
    """Sempre devolve exatamente UM nível e o sinal que o definiu (H3.1.3 T2/T3).

    nivel_atual: o que a leitura do documento já indicou (hoje vem do LLM da extração).
    """
    sinais = {n: [] for n in NivelPrioridade}
    motivos, achado, trecho = [], None, None
    texto = texto or ""

    candidatos = buscar_candidatos(texto, regras.get("achados_criticos", {}))
    restantes, outros = list(candidatos), []
    if confirmador is not None:
        try:
            restantes, outros = _aplicar_confirmacao(texto, candidatos, confirmador(texto, candidatos))
        except Exception:                       # LLM fora do ar: fica como a regra textual decidiu
            restantes, outros = list(candidatos), []
            if candidatos:
                motivos.append("confirmação do LLM indisponível: achado mantido como Urgente")
    if restantes:
        achado, trecho = restantes[0].achado, restantes[0].trecho
        sinais[NivelPrioridade.URGENTE].append(f"achado crítico: {achado}")
    elif outros:
        achado = outros[0]
        sinais[NivelPrioridade.URGENTE].append(f"achado crítico: {achado} (apontado na revisão do texto)")

    if nivel_atual is not None:
        atual = NivelPrioridade(nivel_atual)
        if atual != NivelPrioridade.ROTINA:
            sinais[atual].append(f"prioridade {atual.value} indicada na leitura do documento")

    norm = normalizar(texto)
    for termo in regras.get("termos_urgencia", []):
        if _padrao(termo).search(norm):
            sinais[NivelPrioridade.PRIORITARIO].append(f'termo "{termo}" no texto')
            break
    canal_norm = normalizar(canal or "")
    for c in regras.get("canais_prioritarios", []):
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
        "AVC": ["AVC", "AVCI", "AVCH", "acidente vascular cerebral", "acidente vascular encefálico"],
        "Sepse": ["sepse", "choque séptico", "sepsis"],
        "Dissecção de aorta": ["dissecção de aorta", "dissecção aórtica", "dissecção aguda de aorta"],
        "Hemorragia intracraniana": ["hemorragia intracraniana", "hemorragia intracerebral",
                                     "hemorragia subaracnóidea", "hematoma intracraniano"],
    },
    "termos_urgencia": ["urgente", "urgência", "emergência", "imediato", "CITO"],
    "canais_prioritarios": ["Pronto_Socorro"],
}


def carregar_regras(caminho=None) -> dict:
    """config/regras.json por cima dos padrões: se o arquivo não tiver as chaves, vale o padrão."""
    regras = {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in REGRAS_PADRAO.items()}
    try:
        dados = json.loads(open(caminho, encoding="utf-8-sig").read()) if caminho else {}
    except (OSError, ValueError, TypeError):
        dados = {}
    for chave in regras:
        if chave in dados and dados[chave]:
            regras[chave] = dados[chave]
    return regras


def fazer_confirmador(chamar_llm: Callable[[str], str]) -> Confirmador:
    """Transforma uma função `prompt -> texto` (a chamada ao Gemini) no confirmador (H3.1.1 T3).

    Qualquer erro (rede, JSON quebrado) levanta exceção e `avaliar_urgencia` mantém o achado Urgente.
    """
    def confirmador(texto: str, candidatos: list) -> dict:
        bruto = chamar_llm(montar_prompt(texto, candidatos)).strip()
        bruto = re.sub(r"^```(?:json)?|```$", "", bruto, flags=re.MULTILINE).strip()
        return json.loads(bruto)
    return confirmador
