from fastapi import APIRouter, Depends

from app.modelos import DocumentoEntrada
from app.servicos.armazenamento import (
    Armazenamento,
    DocumentoJaExisteError,
    ObjetoJaExisteError,
    caminho_recebido,
    criar_armazenamento,
)

router = APIRouter()


def obter_armazenamento() -> Armazenamento:
    return criar_armazenamento()


@router.post("/triagem", status_code=201)
def receber_documento(
    documento: DocumentoEntrada,
    armazenamento: Armazenamento = Depends(obter_armazenamento),
):
    # O original é gravado ANTES de qualquer processamento: se o grafo falhar, o texto não se perde.
    try:
        armazenamento.salvar(caminho_recebido(documento.documento_id), documento.documento_texto)
    except ObjetoJaExisteError:
        raise DocumentoJaExisteError(documento.documento_id) from None

    # T4+: iniciar o grafo de triagem aqui
    return {"status": "recebido", "documento_id": documento.documento_id}
