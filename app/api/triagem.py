from fastapi import APIRouter, Depends

from app.modelos import DocumentoEntrada
from app.servicos.armazenamento import ArmazenamentoLocal

router = APIRouter()


def obter_armazenamento() -> ArmazenamentoLocal:
    return ArmazenamentoLocal()


@router.post("/triagem", status_code=201)
def receber_documento(
    documento: DocumentoEntrada,
    armazenamento: ArmazenamentoLocal = Depends(obter_armazenamento),
):
    armazenamento.salvar_recebido(documento)
    return {"status": "recebido", "documento_id": documento.documento_id}