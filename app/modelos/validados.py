from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

Obrigatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Base(BaseModel):
    @field_validator("*", mode="after")
    @classmethod
    def _nao_vazio(cls, v):
        if v.strip().lower() == "não encontrado":
            raise ValueError("não encontrado")
        return v


class ReceitaValidada(_Base):
    nome_paciente: Obrigatorio
    medicamento: Obrigatorio
    dose: Obrigatorio
    crm: Obrigatorio


class GuiaValidada(_Base):
    procedimento: Obrigatorio
    medico_solicitante: Obrigatorio
