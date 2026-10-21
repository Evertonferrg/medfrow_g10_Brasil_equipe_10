import os
import threading
from functools import lru_cache
from typing import Protocol
from urllib.parse import quote

import oci

BUCKET_PADRAO = "mediflow-documentos-clinicos"
PREFIXO_RECEBIDOS = "recebidos/"


class ObjetoJaExisteError(Exception):
    pass


class ObjetoNaoEncontradoError(Exception):
    pass


class ArmazenamentoIndisponivelError(Exception):
    pass


class DocumentoJaExisteError(Exception):
    def __init__(self, documento_id: str):
        super().__init__(documento_id)
        self.documento_id = documento_id


def caminho_recebido(documento_id: str) -> str:
    # quote impede que um id como "a/b" ou "../x" crie subpastas no bucket
    return f"{PREFIXO_RECEBIDOS}{quote(documento_id, safe='')}.txt"


class Armazenamento(Protocol):
    def salvar(self, caminho: str, conteudo: str | bytes, sobrescrever: bool = False) -> None: ...
    def ler(self, caminho: str) -> bytes: ...
    def existe(self, caminho: str) -> bool: ...
    def listar(self, prefixo: str = "") -> list[str]: ...


class ServicoArmazenamento:
    """Armazenamento no OCI Object Storage (camada Always Free)."""

    def __init__(self, bucket: str = BUCKET_PADRAO, cliente=None, namespace: str | None = None):
        if cliente is None:
            try:
                config = oci.config.from_file(profile_name=os.getenv("OCI_PROFILE", "DEFAULT"))
                cliente = oci.object_storage.ObjectStorageClient(config)
            except Exception as e:
                raise ArmazenamentoIndisponivelError("credenciais OCI não configuradas") from e
        self._cliente = cliente
        self._bucket = bucket
        self._namespace = namespace

    def _ns(self) -> str:
        if self._namespace is None:
            self._namespace = self._cliente.get_namespace().data
        return self._namespace

    def _chamar(self, operacao):
        """Executa a chamada ao OCI traduzindo os erros do SDK para os do projeto."""
        try:
            return operacao()
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                raise ObjetoNaoEncontradoError(str(e.message)) from e
            if e.status == 412:
                raise ObjetoJaExisteError(str(e.message)) from e
            raise ArmazenamentoIndisponivelError(f"erro OCI {e.status}") from e
        except oci.exceptions.RequestException as e:  # timeout / sem conexão
            raise ArmazenamentoIndisponivelError("falha de conexão com o OCI") from e

    def salvar(self, caminho: str, conteudo: str | bytes, sobrescrever: bool = False) -> None:
        if isinstance(conteudo, str):
            corpo, tipo = conteudo.encode("utf-8"), "text/plain; charset=utf-8"
        else:
            corpo, tipo = conteudo, "application/octet-stream"
        extra = {"content_type": tipo}
        if not sobrescrever:
            extra["if_none_match"] = "*"  # só grava se o objeto ainda não existir
        self._chamar(
            lambda: self._cliente.put_object(self._ns(), self._bucket, caminho, corpo, **extra)
        )

    def ler(self, caminho: str) -> bytes:
        resposta = self._chamar(
            lambda: self._cliente.get_object(self._ns(), self._bucket, caminho)
        )
        return resposta.data.content

    def existe(self, caminho: str) -> bool:
        try:
            self._chamar(lambda: self._cliente.head_object(self._ns(), self._bucket, caminho))
            return True
        except ObjetoNaoEncontradoError:
            return False

    def listar(self, prefixo: str = "") -> list[str]:
        nomes: list[str] = []
        inicio = None
        while True:
            resposta = self._chamar(
                lambda: self._cliente.list_objects(
                    self._ns(), self._bucket, prefix=prefixo, start=inicio
                )
            )
            nomes.extend(obj.name for obj in resposta.data.objects)
            inicio = resposta.data.next_start_with
            if not inicio:
                return nomes


class ArmazenamentoEmMemoria:
    """Dublê para testes: mesma interface do ServicoArmazenamento, sem rede."""

    def __init__(self):
        self._objetos: dict[str, bytes] = {}
        self._trava = threading.Lock()

    def salvar(self, caminho: str, conteudo: str | bytes, sobrescrever: bool = False) -> None:
        corpo = conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo
        with self._trava:
            if not sobrescrever and caminho in self._objetos:
                raise ObjetoJaExisteError(caminho)
            self._objetos[caminho] = corpo

    def ler(self, caminho: str) -> bytes:
        try:
            return self._objetos[caminho]
        except KeyError:
            raise ObjetoNaoEncontradoError(caminho) from None

    def existe(self, caminho: str) -> bool:
        return caminho in self._objetos

    def listar(self, prefixo: str = "") -> list[str]:
        return sorted(n for n in self._objetos if n.startswith(prefixo))


@lru_cache
def criar_armazenamento() -> Armazenamento:
    # MEDIFLOW_ARMAZENAMENTO=memoria permite rodar a API sem credenciais OCI (dados se perdem ao reiniciar)
    if os.getenv("MEDIFLOW_ARMAZENAMENTO", "oci") == "memoria":
        return ArmazenamentoEmMemoria()
    return ServicoArmazenamento(os.getenv("OCI_BUCKET", BUCKET_PADRAO))
