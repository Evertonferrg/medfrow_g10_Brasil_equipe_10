
import json
import os
import pathlib
import re
from functools import lru_cache
from . import config
 
_CAMINHO_OK = re.compile(r"^[\w\-./]+$")
 
 
def _seguro(caminho: str) -> str:
    """Recusa caminhos absolutos, '..' e caracteres estranhos (path traversal)."""
    if not _CAMINHO_OK.match(caminho) or caminho.startswith("/") or ".." in caminho.split("/"):
        raise ValueError(f"caminho inválido: {caminho!r}")
    return caminho
 
 
def _local(caminho: str) -> pathlib.Path:
    base = (pathlib.Path(config.pasta_local()) / config.bucket()).resolve()
    destino = (base / _seguro(caminho)).resolve()
    if base not in destino.parents:
        raise ValueError(f"caminho fora do bucket: {caminho!r}")
    return destino
 
 
def _salvar_local(caminho: str, dados: bytes):
    destino = _local(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(dados)
 
 
@lru_cache(maxsize=1)
def _cliente_oci():
    import oci   # só é exigido quando o OCI é usado
    cfg = oci.config.from_file(os.path.expanduser(os.getenv("OCI_CONFIG_FILE", "~/.oci/config")))
    return oci.object_storage.ObjectStorageClient(cfg)
 
 
def _salvar_oci(namespace: str, caminho: str, dados: bytes):
    _cliente_oci().put_object(namespace, config.bucket(), caminho, dados)
 
 
def salvar(caminho: str, conteudo) -> dict:
    """Salva texto, bytes ou dicionário. Devolve onde e como foi salvo."""
    _seguro(caminho)
    if isinstance(conteudo, (bytes, bytearray)):
        dados = bytes(conteudo)
    elif isinstance(conteudo, str):
        dados = conteudo.encode("utf-8")
    else:
        dados = json.dumps(conteudo, ensure_ascii=False, indent=2).encode("utf-8")
    ns = os.getenv("OCI_NAMESPACE")
    base = {"bucket": config.bucket(), "caminho_objeto": caminho}
    if ns:
        try:
            _salvar_oci(ns, caminho, dados)
            return {**base, "local": "oci", "status_backup": "sucesso"}
        except Exception as e:           # falhou: não perde o documento
            _salvar_local(caminho, dados)
            return {**base, "local": "disco",
                    "status_backup": f"oci_falhou_salvo_local: {str(e)[:80]}"}
    _salvar_local(caminho, dados)
    return {**base, "local": "disco", "status_backup": "sucesso"}
 
 
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
 