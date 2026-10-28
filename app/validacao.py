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
    "posologia_nao_confirmada": 0.15, #h1.3.4
    "exame_inventado": 0.30,# h1.3.5
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
 
#H1.3.4 medicamentos e posologia
CAMPO_FALTANTE = "campo faltante: "
CAMPO_NAO_CONFIRMADO = "campo não confirmado no texto: "
JANELA_MEDICAMENTO = 400 

def _achar_frase(frase_s: str, texto_s: str):
    """(inicio, fim) da 1º ocorrência da frase como palavras interias, ou Nome.
    Os dois textos já devem estar simplificados (sem acento, minusculas, espaços simples)."""
    if not frase_s:
        return None
    m = re.search(rf"(?<!\w){re.escape(frase_s)}(?!\w)", texto_s)
    return (m.start(), m.end()) if m else None

def _dose_normalizada(dose: str) -> str:
    return re.sub(r"\s+", "", _simplificar(dose).replace(",", "."))

def _dose_na_janela(dose: str, janela_s: str) -> bool:
    """'500mg' = '500 mg' , mas  '5mg' NÃO casa como '25mg' nem '1.5mg', e não há conversão de unidade."""
    alvo = _dose_normalizada(dose)
    if not alvo:
        return False
    junto = re.sub(r"\s+", "", janela_s.replace(",", "."))
    return bool(re.search(rf"(?<![\d.]){re.escape(alvo)}(?!\d)", junto))


def _numeros(s: str) -> set:
    return set(re.findall(r"\d+(?:\.\d+)?", s.replace(",", ".")))


def _valor_na_janela(valor: str, janela_s: str) -> bool:
    """Via, frequência e duração: a frase escrita aparece na janela ou, se houver números,
    todos os números do valor aparecem nela (aceita '8/8h' para 'de 8 em 8 horas';
    nunca aceita um número que não esteja no documento)."""
    v = _simplificar(valor)
    if not v:
        return False
    if _achar_frase(v, janela_s):
        return True
    nums = _numeros(v)
    return bool(nums) and nums <= _numeros(janela_s)


def _validar_medicamentos(extracao: Extracao, texto_s: str):
    """Um item por medicamento, todos presentes no texto. Dose, via, frequência e duração só ficam
    se confirmadas NA REGIÃO do texto desse medicamento; o resto vira null e é sinalizado.
    Receita sem dose: 'campo faltante: dose'. Devolve (problemas, penalidade)."""
    problemas, pen = [], 0.0
    e_receita = extracao.tipo_documento == "Receituário Médico"

    candidatos, vistos = [], set()
    for m in extracao.medicamentos:
        nome_s = _simplificar(m.nome)
        pos = _achar_frase(nome_s, texto_s)
        if pos is None and nome_s:
            pos = _achar_frase(nome_s.split()[0], texto_s)      # 'Dipirona sódica' -> 'Dipirona'
        if pos is None:
            problemas.append(f"Medicamento '{m.nome}' não encontrado no texto original")
            pen += PENALIDADES["medicamento_inventado"]
            continue
        chave = (nome_s.split()[0], _dose_normalizada(m.dose or ""))
        if chave in vistos:                                        # mesmo medicamento repetido
            continue
        vistos.add(chave)
        candidatos.append((m, pos[0]))

    inicios = sorted({ini for _, ini in candidatos})
    mantidos = []
    for m, ini in candidatos:
        seguintes = [i for i in inicios if i > ini]
        fim = min(seguintes[0] if seguintes else ini + JANELA_MEDICAMENTO, ini + JANELA_MEDICAMENTO)
        janela = texto_s[ini:fim]
        tinha_dose = bool(m.dose)
        for campo, confere in (("dose", _dose_na_janela), ("via", _valor_na_janela),
                               ("frequencia", _valor_na_janela), ("duracao", _valor_na_janela)):
            valor = getattr(m, campo)
            if valor and not confere(valor, janela):
                problemas.append(f"{CAMPO_NAO_CONFIRMADO}{campo} (medicamento '{m.nome}')")
                pen += PENALIDADES["posologia_nao_confirmada"]
                setattr(m, campo, None)
        if e_receita and not tinha_dose:
            problemas.append(f"{CAMPO_FALTANTE}dose | Medicamento '{m.nome}' sem dose informada")
            pen += PENALIDADES["posologia_incompleta"]
        mantidos.append(m)
    extracao.medicamentos = mantidos
    return problemas, pen

#h1.3.5 exames e procedimentos
DISTANCIA_MAXIMA_TUSS = 300

def _padrao_tuss(digitos: str) -> str:
    """Os digitos do código, com ponto, hifen ou espaço opicionais entre eles, sem colocar em outro número. """
    return r"(?<!\d)" + r"[.\-\s]?".join(digitos) + r"(?!\d)"

def _distancia(posicao: int, trecho) -> int:
    return max(trecho[0] - posicao, posicao - trecho[1], 0)

def _validar_exames(extracao: Extracao, texto_s: str):
    """Um item por exame, todos presentes no texto, sem duplicatas. O código TUSS só fica se estiver
    escrito no documento, inteiro e junto DESSE exame (não de outro). Devolve (problemas, penalidade)."""
    problemas, pen = [], 0.0

    unicos = {}
    for e in extracao.exames:                          # funde duplicatas; o código não se perde
        chave = _simplificar(e.nome)
        if chave in unicos:
            if not unicos[chave].codigo_tuss and e.codigo_tuss:
                unicos[chave].codigo_tuss = e.codigo_tuss
            continue
        unicos[chave] = e

    achados = []
    for chave, e in unicos.items():
        pos = _achar_frase(chave, texto_s)
        if pos is None:
            problemas.append(f"Exame '{e.nome}' não encontrado no texto original")
            pen += PENALIDADES["exame_inventado"]
            continue
        achados.append((e, pos))

    todos = [pos for _, pos in achados]
    for e, pos in achados:
        if not e.codigo_tuss:
            continue
        digitos = re.sub(r"\D", "", e.codigo_tuss)
        ocorrencias = [m.start() for m in re.finditer(_padrao_tuss(digitos), texto_s)] if digitos else []
        if not ocorrencias:
            problemas.append(f"Código TUSS {e.codigo_tuss} não encontrado no texto original")
            pen += PENALIDADES["tuss_nao_encontrado"]
            e.codigo_tuss = None
            continue
        limite = None if len(achados) == 1 else DISTANCIA_MAXIMA_TUSS
        junto = any(
            _distancia(o, pos) <= min(_distancia(o, outro) for outro in todos)
            and (limite is None or _distancia(o, pos) <= limite)
            for o in ocorrencias)
        if junto:
            e.codigo_tuss = digitos                     # forma canônica: só dígitos
        else:
            problemas.append(f"Código TUSS {e.codigo_tuss} não está junto do exame '{e.nome}' no texto")
            pen += PENALIDADES["tuss_nao_encontrado"]
            e.codigo_tuss = None
    extracao.exames = [e for e, _ in achados]
    return problemas, pen

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
 
    # 5) Medicamentos: descarta inventados, confere posologia na região do medicamento
    p, d = _validar_medicamentos(extracao, texto_s)
    problemas += p; pen += d

    # 6) Exames: funde duplicatas, descarta inventados, confere TUSS junto do exame
    p, d = _validar_exames(extracao, texto_s)
    problemas += p; pen += d
 
    # 7) Evidências: só ficam os trechos que realmente existem no documento
    extracao.evidencias = [ev for ev in extracao.evidencias
                           if ev.trecho and _simplificar(ev.trecho) in texto_s]
 
    # 8) Score final: base do LLM limitada a 0.95 menos as penalidades
    base = min(extracao.score_confianca_classificacao, 0.95)
    return extracao, problemas, max(0.0, round(base - pen, 2))
 
 
def precisa_revisao(score: float, problemas: list) -> bool:
    """Score baixo OU qualquer problema encontrado."""
    return score < config.limiar_confianca() or len(problemas) > 0