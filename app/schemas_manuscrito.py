from pydantic import BaseModel

ILEGIVEL = "ilegível"


class CampoLido(BaseModel):
    valor: str | None  # None = o campo não está escrito na receita
    score: float  # 0 a 1: certeza da leitura


class MedicamentoManuscrito(BaseModel):
    nome: CampoLido
    dose: CampoLido
    frequencia: CampoLido


class LeituraManuscrita(BaseModel):
    paciente: CampoLido
    medicamentos: list[MedicamentoManuscrito]
