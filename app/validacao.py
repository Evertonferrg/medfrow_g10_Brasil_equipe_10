
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
 
 
def _simplificar(texto: str) -> str:
    """Sem acentos, minúsculas e espaços normalizados, para comparar textos."""
    t = unicodedata.normalize("NFD", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().split())
 
 
def normalizar_crm(crm):
    """'CRM-SP 145892' (e variações) -> '145892-SP'. None se faltar número ou UF válida."""
    if not crm:
        return None
    numero = re.search(r"\d{3,7}", crm)
    candidatas = re.findall(r"\b([A-Za-z]{2})\b", crm.upper().replace("CRM", ""))
    ufs = [c for c in candidatas if c in UFS_VALIDAS]
    if numero and ufs:
        return f"{numero.group()}-{ufs[0]}"
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
    if not bruto:
        problemas.append("CRM do solicitante não encontrado"); pen += PENALIDADES["crm_ausente"]
    elif not crm:
        problemas.append(f"CRM em formato inválido: '{bruto}'"); pen += PENALIDADES["crm_ausente"]
    elif crm.split("-")[0] not in re.sub(r"[.\s]", "", texto):
        problemas.append(f"CRM {crm} não consta no texto original"); pen += PENALIDADES["crm_ausente"]
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
 
    # 4) CID: formato válido? está escrito no documento ou é só "sugerido"?
    if extracao.cid_sugerido:
        cid = extracao.cid_sugerido.strip().upper()
        if CID_REGEX.match(cid):
            extracao.cid_sugerido = cid
            extracao.cid_origem = "documento" if cid.lower() in texto.lower() else "sugerido"
        else:
            problemas.append(f"CID inválido: '{extracao.cid_sugerido}'")
            pen += PENALIDADES["cid_invalido"]
            extracao.cid_sugerido, extracao.cid_origem = None, None
 
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
 
 
def precisa_revisao(score: float, problemas: list) -> bool:
    """Score baixo OU qualquer problema encontrado."""
    return score < config.limiar_confianca() or len(problemas) > 0
 