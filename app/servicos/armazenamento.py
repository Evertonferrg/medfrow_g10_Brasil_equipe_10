from pathlib import Path
from urllib.parse import quote

from app.modelos import DocumentoEntrada

class DocumentoJaExisteError(Exception):
    def __init__(self, documento_id:str):
        super().__init__(documento_id)
        self.documento_id = documento_id

class ArmazenamentoLocal:
    """Guarda os documentos em <base>/recebidos/. Será torcado pelo OCI depois."""

    def __init__(self, base_dir: str | Path = "aramazenamento"):
        self.pasta_recebidos = Path(base_dir) / "recebidos"
        self.pasta_recebidos.mkdir(parents=True, exist_ok=True)

    def _caminho(self, documento_id: str) -> Path:
        #impede que um id como "../x" escape da pasta
        return self.pasta_recebidos / f"{quote(documento_id, safe='')}.json"

    def salvar_recebido(self, documento: DocumentoEntrada) -> None:
        try:
            #cria arquivo só se nao existir
            with open(self._caminho(documento.documento_id), "x", encoding="utf-8") as f:
                f.write(documento.model_dump_json(indent=2))
        except FileExistsError:
            raise DocumentoJaExisteError(documento.documento_id) from None
    