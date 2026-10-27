
import csv
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
from . import config
from .schemas import Extracao
 
UFS_VALIDAS = {"AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG",
               "PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"}
 
# Quanto cada problema desconta do score (ajustável)
PENALIDADES = {
    "paciente_ausente": 0.30, "crm_ausente": 0.25, "tipo_desconhecido": 0.40,
    "inconsistencia": 0.20, "nome_nao_encontrado": 0.30,
    "medicamento_inventado": 0.30, "posologia_incompleta": 0.15,
    "tuss_nao_encontrado": 0.20, "cid_invalido": 0.10,
}
CID_REGEX = re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$")
ARQUIVO_CID10 = Path(__file__).resolve().parents[1] / "config" / "cid10.csv"


@lru_cache(maxsize=1)
def carregar_cids_validos(caminho: Path | None = None) -> frozenset[str]:
    """H1.3.3 T2: carrega a tabela CID-10 do CSV uma única vez num conjunto imutável."""
    alvo = caminho or ARQUIVO_CID10
    codigos: set[str] = set()
    with alvo.open(encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            codigo = (linha.get("codigo") or "").strip().upper()
            if codigo:
                codigos.add(codigo)
    return frozenset(codigos)
 
 
def _simplificar(texto: str) -> str:
    """Sem acentos, minúsculas e espaços normalizados, para comparar textos."""
    t = unicodedata.normalize("NFD", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().split())
 
 
def normalizar_crm(crm):
    """'CRM-SP 145892' (e variações) -> '145892-SP'. None se faltar número ou UF válida."""
    if not crm or not isinstance(crm, str):
        return None
    limpo = re.sub(r"(?<=\d)\.(?=\d)", "", crm.strip())
    numeros = re.findall(r"\d+", limpo)
    candidatas = re.findall(r"\b([A-Za-z]{2})\b", limpo.upper().replace("CRM", " "))
    ufs = [c for c in candidatas if c in UFS_VALIDAS]
    if len(numeros) == 1 and 3 <= len(numeros[0]) <= 7 and len(ufs) == 1 and len(candidatas) == 1:
        return f"{numeros[0]}-{ufs[0]}"
    return None
 
 
def _nome_aparece_no_texto(nome: str, texto: str) -> bool:
    """TODAS as palavras do nome precisam existir no texto (ignora Dr./Dra.),
    como palavras inteiras (assim 'ana' não casa com 'banana')."""
    palavras_texto = set(re.findall(r"\w+", _simplificar(texto)))
    palavras = [p for p in re.findall(r"\w+", _simplificar(nome)) if p not in ("dr", "dra")]
    return all(p in palavras_texto for p in palavras)
 
 
def validar(extracao: Extracao, texto: str):
    """Devolve (extracao_corrigida, lista_de_problemas, score_final)."""
    problemas, pen = [], 0.0
    texto_s = _simplificar(texto)
 
    # 1) CRM: normaliza e confere o número no texto (nunca um valor "plausível")
    bruto = extracao.medico_solicitante.crm
    crm = normalizar_crm(bruto)
    erro_crm = None
    if not bruto:
        erro_crm = "CRM do solicitante não encontrado"
        problemas.append(erro_crm); pen += PENALIDADES["crm_ausente"]
    elif not crm:
        erro_crm = f"CRM em formato inválido: '{bruto}'"
        problemas.append(erro_crm); pen += PENALIDADES["crm_ausente"]
    elif crm.split("-")[0] not in re.sub(r"[.\s]", "", texto):
        erro_crm = f"CRM {crm} não consta no texto original"
        problemas.append(erro_crm); pen += PENALIDADES["crm_ausente"]
        crm = None
    extracao.medico_solicitante.crm = crm
 
    # 2) Paciente e médico: o nome existe no texto?
    nome = extracao.paciente.nome
    if not nome:
        problemas.append("Nome do paciente ausente"); pen += PENALIDADES["paciente_ausente"]
    elif not _nome_aparece_no_texto(nome, texto):
        problemas.append(f"Nome '{nome}' não encontrado no texto original")
        pen += PENALIDADES["nome_nao_encontrado"]
    medico = extracao.medico_solicitante.nome
    if medico and not _nome_aparece_no_texto(medico, texto):
        problemas.append(f"Nome do médico '{medico}' não encontrado no texto original")
        pen += PENALIDADES["nome_nao_encontrado"]
 
    # 3) Tipo e inconsistências apontadas pelo LLM
    if extracao.tipo_documento == "Desconhecido":
        problemas.append("Tipo de documento não identificado"); pen += PENALIDADES["tipo_desconhecido"]
    for item in extracao.inconsistencias:
        problemas.append(f"Inconsistência: {item}"); pen += PENALIDADES["inconsistencia"]
    if erro_crm and erro_crm not in extracao.inconsistencias:
        extracao.inconsistencias.append(erro_crm)
 
    # 4) CID: formato válido e presente na tabela CID-10? Está escrito ou sugerido?
    if extracao.cid_sugerido:
        cid_bruto = extracao.cid_sugerido.strip().upper()
        cid = (
            f"{cid_bruto[:3]}.{cid_bruto[3:]}"
            if re.match(r"^[A-Z]\d{3,4}$", cid_bruto)
            else cid_bruto
        )
        cids_validos = carregar_cids_validos()
        if CID_REGEX.match(cid) and cid in cids_validos:
            extracao.cid_sugerido = cid
            texto_lower = texto.lower()
            escrito = cid.lower() in texto_lower or cid.replace(".", "").lower() in texto_lower
            origem = "escrito" if escrito else "sugerido"
            extracao.origem_cid = origem
            extracao.cid_origem = origem
        else:
            problemas.append(f"CID inválido: '{extracao.cid_sugerido}'")
            pen += PENALIDADES["cid_invalido"]
            extracao.cid_sugerido = None
            extracao.origem_cid = None
            extracao.cid_origem = None
 
    # 5) Medicamentos: descarta inventados; receita sem dose é sinalizada
    mantidos = []
    for m in extracao.medicamentos:
        primeira = (_simplificar(m.nome).split() or [""])[0]
        if primeira and primeira not in texto_s:
            problemas.append(f"Medicamento '{m.nome}' não encontrado no texto original")
            pen += PENALIDADES["medicamento_inventado"]
            continue
        if extracao.tipo_documento == "Receituário Médico" and not m.dose:
            problemas.append(f"Medicamento '{m.nome}' sem dose informada")
            pen += PENALIDADES["posologia_incompleta"]
        mantidos.append(m)
    extracao.medicamentos = mantidos
 
    # 6) Exames: remove duplicatas e confere o código TUSS no texto
    vistos, exames = set(), []
    for e in extracao.exames:
        chave = _simplificar(e.nome)
        if chave in vistos:
            continue
        vistos.add(chave)
        if e.codigo_tuss and e.codigo_tuss not in texto:
            problemas.append(f"Código TUSS {e.codigo_tuss} não encontrado no texto original")
            pen += PENALIDADES["tuss_nao_encontrado"]
            e.codigo_tuss = None
        exames.append(e)
    extracao.exames = exames
 
    # 7) Evidências: só ficam os trechos que realmente existem no documento
    extracao.evidencias = [ev for ev in extracao.evidencias
                           if ev.trecho and _simplificar(ev.trecho) in texto_s]
 
    # 8) Score final: base do LLM limitada a 0.95 menos as penalidades
    base = min(extracao.score_confianca_classificacao, 0.95)
    return extracao, problemas, max(0.0, round(base - pen, 2))
 
 
def motivo_revisao(score: float, problemas: list, limite: float, erro: str | None = None) -> str:
    """Motivo registrado no estado quando o documento não é roteado sozinho.

    A ordem espelha a decisão do grafo: falha de extração, baixa confiança,
    depois os problemas de validação.
    """
    if erro:
        return f"falha na extração automática ({erro[:80]})"
    if score < limite:
        motivo = "baixa confiança na classificação"
        if problemas:
            motivo += f"; {'; '.join(problemas)}"
        return motivo
    return "; ".join(problemas) or "revisão necessária"


def precisa_revisao(score: float, problemas: list, limite: float | None = None) -> bool:
    """Score baixo OU qualquer problema encontrado."""
    if limite is None:
        limite = config.limite_confianca()
    return score < limite or len(problemas) > 0


def taxa_acerto_por_faixa(avaliacoes: list[dict], limite: float | None = None) -> dict:
    """H1.2.2 T1: calcula a taxa de acerto abaixo e acima do limite de confiança.

    Cada item de 'avaliacoes' deve ter:
      - 'esperado': tipo de documento correto
      - 'obtido': tipo de documento classificado
      - 'score': score de confiança (0 a 1)
    """
    if limite is None:
        limite = config.limite_confianca()
    abaixo = [a for a in avaliacoes if a["score"] < limite]
    acima = [a for a in avaliacoes if a["score"] >= limite]

    def _resumo(itens: list[dict]) -> dict:
        total = len(itens)
        acertos = sum(1 for i in itens if i["esperado"] == i["obtido"])
        return {
            "total": total,
            "acertos": acertos,
            "taxa_acerto": round(acertos / total, 2) if total else 0.0,
        }

    return {
        "limite": limite,
        "abaixo_do_limite": _resumo(abaixo),
        "acima_ou_igual_ao_limite": _resumo(acima),
    }
