from pydantic import BaseModel, field_validator


class DocumentoEntrada(BaseModel):
    documento_id: str
    tipo_arquivo: str
    documento_texto: str
    canal_origem: str

    @field_validator("documento_texto")
    @classmethod
    def recusar_texto_vazio(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("documento vazio")
        return valor
