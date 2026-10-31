import json
import os
import pathlib
import re
from functools import lru_cache
from . import config

_CAMINHO_OK = re.compile(r"[\w\-./]+")

# H5.1.1 T2: formatos aceitos em recebidos/ e o content-type de cada um
CONTENT_TYPES = {
    ".txt": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".png": "image/png",
}
EXTENSOES = tuple(CONTENT_TYPES)


class ObjetoJaExisteError(Exception):
    """Tentativa de gravar (sem sobrescrever) um objeto que já existe."""


def _seguro(caminho: str) -> str:
    """Recusa caminhos absolutos, '..' e caracteres estranhos (path traversal)."""
    if not _CAMINHO_OK.fullmatch(caminho) or caminho.startswith("/") or ".." in caminho.split("/"):
        raise ValueError(f"caminho inválido: {caminho!r}")
    return caminho


def _local(caminho: str) -> pathlib.Path:
    base = (pathlib.Path(config.pasta_local()) / config.bucket()).resolve()
    destino = (base / _seguro(caminho)).resolve()
    if base not in destino.parents:
        raise ValueError(f"caminho fora do bucket: {caminho!r}")
    return destino


def _salvar_local(caminho: str, dados: bytes, sobrescrever: bool = True):
    destino = _local(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if sobrescrever:
        destino.write_bytes(dados)
        return
    try:
        with open(destino, "xb") as f:      # "x": falha se já existir (atômico)
            f.write(dados)
    except FileExistsError:
        raise ObjetoJaExisteError(caminho) from None


@lru_cache(maxsize=1)
def _cliente_oci():
    import oci   # só é exigido quando o OCI é usado
    cfg = oci.config.from_file(os.path.expanduser(os.getenv("OCI_CONFIG_FILE", "~/.oci/config")))
    return oci.object_storage.ObjectStorageClient(cfg)


def _salvar_oci(namespace: str, caminho: str, dados: bytes, sobrescrever: bool = True,
                content_type: str | None = None):
    extra = {}
    if not sobrescrever:
        extra["if_none_match"] = "*"            # só grava se ainda não existir (H5.1.1 T4)
    if content_type:
        extra["content_type"] = content_type    # H5.1.1 T2
    try:
        _cliente_oci().put_object(namespace, config.bucket(), caminho, dados, **extra)
    except Exception as e:
        if getattr(e, "status", None) == 412:                # objeto já existe
            raise ObjetoJaExisteError(caminho) from e
        raise


def salvar(caminho: str, conteudo, sobrescrever: bool = True, content_type: str | None = None) -> dict:
    """Salva texto, bytes ou dicionário. Devolve onde e como foi salvo.

    Com sobrescrever=False, levanta ObjetoJaExisteError se o objeto já existir
    (usado para o original em recebidos/, que nunca pode ser trocado).
    """
    _seguro(caminho)
    if isinstance(conteudo, (bytes, bytearray)):
        dados = bytes(conteudo)
    elif isinstance(conteudo, str):
        dados = conteudo.encode("utf-8")
    else:
        dados = json.dumps(conteudo, ensure_ascii=False, indent=2).encode("utf-8")
        content_type = content_type or "application/json"
    if not sobrescrever and _local(caminho).exists():        # já está no disco (fallback antigo)
        raise ObjetoJaExisteError(caminho)
    ns = os.getenv("OCI_NAMESPACE")
    base = {"bucket": config.bucket(), "caminho_objeto": caminho}
    if ns:
        try:
            _salvar_oci(ns, caminho, dados, sobrescrever, content_type)
            return {**base, "local": "oci", "status_backup": "sucesso"}
        except ObjetoJaExisteError:
            raise
        except Exception as e:           # falhou: não perde o documento
            _salvar_local(caminho, dados, sobrescrever)
            return {**base, "local": "disco",
                    "status_backup": f"oci_falhou_salvo_local: {str(e)[:80]}"}
    _salvar_local(caminho, dados, sobrescrever)
    return {**base, "local": "disco", "status_backup": "sucesso"}


def salvar_original(documento_id: str, conteudo: bytes, extensao: str) -> dict:
    """H5.1.1 T2: ÚNICO ponto que grava o original em recebidos/<documento_id><extensão>.

    - content-type correto para cada formato;
    - escrita condicional: um original nunca é sobrescrito (T4);
    - recusa o ID se ele já foi recebido em OUTRO formato.
    Levanta ObjetoJaExisteError quando o ID já existe.
    """
    if extensao not in CONTENT_TYPES:
        raise ValueError(f"extensão não suportada: {extensao!r}")
    for outra in EXTENSOES:
        if outra != extensao and existe(f"recebidos/{documento_id}{outra}"):
            raise ObjetoJaExisteError(documento_id)
    return salvar(f"recebidos/{documento_id}{extensao}", conteudo,
                  sobrescrever=False, content_type=CONTENT_TYPES[extensao])


def ler(caminho: str):
    """Devolve os bytes do arquivo ou None se não existir."""
    ns = os.getenv("OCI_NAMESPACE")
    if ns:
        try:
            return _cliente_oci().get_object(ns, config.bucket(), _seguro(caminho)).data.content
        except Exception:
            pass                          # não achou na nuvem: tenta o disco
    p = _local(caminho)
    return p.read_bytes() if p.exists() else None


def existe(caminho: str) -> bool:
    return ler(caminho) is not None


def listar(prefixo: str) -> list:
    nomes = set()
    ns = os.getenv("OCI_NAMESPACE")
    if ns:
        try:
            r = _cliente_oci().list_objects(ns, config.bucket(), prefix=prefixo)
            nomes.update(o.name for o in r.data.objects)
        except Exception:
            pass
    base = (pathlib.Path(config.pasta_local()) / config.bucket()).resolve()
    if base.exists():
        nomes.update(str(p.relative_to(base)).replace(os.sep, "/")
                     for p in base.rglob("*") if p.is_file())
    return sorted(n for n in nomes if n.startswith(prefixo))
