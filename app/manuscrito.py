import unicodedata
from collections.abc import Callable

from . import llm
from .schemas_manuscrito import ILEGIVEL, CampoLido, LeituraManuscrita

MOTIVO_REVISAO = "trecho ilegível em receita manuscrita"

# Limite próprio do manuscrito: o Gemini deu 0.95 para letra nítida e 0.5 a 0.8
# para trechos que chutou, então 0.7 deixava passar leitura duvidosa.
LIMITE_MANUSCRITO = 0.85


def _marca_ilegivel(valor: str | None) -> bool:
    if valor is None:
        return False
    sem_acento = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode()
    return "ilegivel" in sem_acento.casefold()


def _limitar(campo: CampoLido, limite: float) -> CampoLido:
    """Score abaixo do limite (ou 'ilegível' vindo do LLM) => 'ilegível' com score 0."""
    if campo.valor is None:
        return campo
    if _marca_ilegivel(campo.valor) or campo.score < limite:
        return CampoLido(valor=ILEGIVEL, score=0.0)
    return campo


def aplicar_limite(
    leitura: LeituraManuscrita, limite_confianca: float
) -> LeituraManuscrita:
    """T2: nome de medicamento e dose abaixo do limite viram 'ilegível',
    mesmo que o LLM tenha arriscado um valor."""
    medicamentos = [
        m.model_copy(
            update={
                "nome": _limitar(m.nome, limite_confianca),
                "dose": _limitar(m.dose, limite_confianca),
            }
        )
        for m in leitura.medicamentos
    ]
    return leitura.model_copy(update={"medicamentos": medicamentos})


def tem_ilegivel(leitura: LeituraManuscrita) -> bool:
    return any(
        c.valor == ILEGIVEL for m in leitura.medicamentos for c in (m.nome, m.dose)
    )


def processar_manuscrita(
    imagens: list[bytes],
    limite_confianca: float,
    enviar_revisao: Callable[[str, str], None],
    documento_id: str,
    ler: Callable[[list[bytes]], LeituraManuscrita] = llm.ler_manuscrita,
) -> tuple[LeituraManuscrita, str]:
    """T3: lê, aplica o limite por campo e encaminha à revisão se houver 'ilegível'."""
    leitura = aplicar_limite(ler(imagens), limite_confianca)
    if tem_ilegivel(leitura):
        enviar_revisao(documento_id, MOTIVO_REVISAO)
        return leitura, "revisao"
    return leitura, "ok"
