import json
import logging
import os
import pathlib
import re
from datetime import UTC, datetime
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

logger = logging.getLogger(__name__)


class ObjetoJaExisteError(Exception):
    """Tentativa de gravar (sem sobrescrever) um objeto que já existe."""


def _seguro(caminho: str) -> str:
    """Recusa caminhos absolutos, '..' e caracteres estranhos (path traversal)."""
    if (
        not _CAMINHO_OK.fullmatch(caminho)
        or caminho.startswith("/")
        or ".." in caminho.split("/")
    ):
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
        with open(destino, "xb") as f:  # "x": falha se já existir (atômico)
            f.write(dados)
    except FileExistsError:
        raise ObjetoJaExisteError(caminho) from None


@lru_cache(maxsize=1)
def _cliente_oci():
    import oci  # só é exigido quando o OCI é usado

    if os.getenv("OCI_AUTH") == "instance_principal":
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        return oci.object_storage.ObjectStorageClient(
            config={"region": signer.region},
            signer=signer,
        )
    else:
        cfg = oci.config.from_file(
            os.path.expanduser(os.getenv("OCI_CONFIG_FILE", "~/.oci/config"))
        )
        return oci.object_storage.ObjectStorageClient(cfg)


def oci_retry_strat():
    import oci

    return oci.retry.RetryStrategyBuilder(
        max_attempts_check=True,
        max_attempts=3,
        total_elapsed_time_check=False,
        service_error_check=True,
        service_error_retry_on_any_5xx=True,
        backoff_type=oci.retry.BACKOFF_FULL_JITTER_EQUAL_ON_THROTTLE_VALUE,
    ).get_retry_strategy()


def _salvar_oci(
    namespace: str,
    caminho: str,
    dados: bytes,
    sobrescrever: bool = True,
    content_type: str | None = None,
):
    extra = {}
    if not sobrescrever:
        extra["if_none_match"] = "*"  # só grava se ainda não existir (H5.1.1 T4)
    if content_type:
        extra["content_type"] = content_type  # H5.1.1 T2
    try:
        _cliente_oci().put_object(
            namespace,
            config.bucket(),
            caminho,
            dados,
            retry_strategy=oci_retry_strat(),
            **extra,
        )
    except Exception as e:
        if getattr(e, "status", None) == 412:  # objeto já existe
            raise ObjetoJaExisteError(caminho) from e
        raise


class FalhaArmazenamentoError(RuntimeError):
    """A persistência definitiva do objeto falhou após os retries."""


def salvar(
    caminho: str, conteudo, sobrescrever: bool = True, content_type: str | None = None
) -> dict:
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
    if (
        not sobrescrever and _local(caminho).exists()
    ):  # já está no disco (fallback antigo)
        raise ObjetoJaExisteError(caminho)
    ns = os.getenv("OCI_NAMESPACE")
    base = {"bucket": config.bucket(), "caminho_objeto": caminho}
    if ns:
        try:
            _salvar_oci(ns, caminho, dados, sobrescrever, content_type)
        except ObjetoJaExisteError:
            logger.exception("O objeto da requisição já existe.")
            raise
        except Exception:  # falhou: não perde o documento
            logger.exception("Falha no armazenamento na OCI após diversas tentativas.")
            _salvar_local(caminho, dados, sobrescrever)
            return {**base, "local": "oci", "status_backup": "falha"}
        return {**base, "local": "oci", "status_backup": "sucesso"}
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
    salvo = salvar(
        f"recebidos/{documento_id}{extensao}",
        conteudo,
        sobrescrever=False,
        content_type=CONTENT_TYPES[extensao],
    )
    if salvo["status_backup"] == "falha":
        raise FalhaArmazenamentoError(
            f"original não gravado: {salvo['caminho_objeto']}"
        )
    return salvo


def ler(caminho: str):
    """Devolve os bytes do arquivo ou None se não existir."""
    ns = os.getenv("OCI_NAMESPACE")
    if ns:
        try:
            r = _cliente_oci().get_object(ns, config.bucket(), _seguro(caminho))
            if r is not None:
                return r.data.content
        except Exception:
            # não achou na nuvem: tenta o disco
            logger.exception("Falha ao consultar OCI; usando armazenamento local")
    p = _local(caminho)
    return p.read_bytes() if p.exists() else None


def existe(caminho: str) -> bool:
    return ler(caminho) is not None


def _mover_local(origem: str, destino: str) -> None:
    src, dst = _local(origem), _local(destino)
    if not src.exists():
        raise FileNotFoundError(origem)
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)  # renomeia, sem cópia


def mover(origem: str, destino: str) -> None:
    """H5.1.3 T1: troca o objeto de prefixo com rename_object, sem cópia intermediária."""
    _seguro(origem)
    _seguro(destino)
    ns = os.getenv("OCI_NAMESPACE")
    if ns:
        try:
            import oci  # só é exigido quando o OCI é usado

            detalhes = oci.object_storage.models.RenameObjectDetails(
                source_name=origem, new_name=destino
            )
            _cliente_oci().rename_object(ns, config.bucket(), detalhes)
            return
        except Exception:
            logger.exception("Falha ao renomear no OCI; tentando o disco")
            if not _local(origem).exists():
                raise  # não há cópia local para mover: não esconde o erro
    _mover_local(origem, destino)


def listar(prefixo: str) -> list:
    nomes = set()
    ns = os.getenv("OCI_NAMESPACE")
    if ns:
        try:
            r = _cliente_oci().list_objects(ns, config.bucket(), prefix=prefixo)
            if r is not None:
                nomes.update(o.name for o in r.data.objects)
        except Exception:
            # não achou na nuvem: tenta o disco
            logger.exception("Falha ao consultar OCI; usando armazenamento local")
    base = (pathlib.Path(config.pasta_local()) / config.bucket()).resolve()
    if base.exists():
        nomes.update(
            str(p.relative_to(base)).replace(os.sep, "/")
            for p in base.rglob("*")
            if p.is_file()
        )
    return sorted(n for n in nomes if n.startswith(prefixo))


def _normalizar_data(valor) -> datetime | None:
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor)
        except ValueError:
            return None
    if not isinstance(valor, datetime):
        return None
    return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


def listar_com_datas(prefixo: str) -> list[tuple[str, datetime | None]]:
    """Lista objetos sob o prefixo com a data de criação/modificação em UTC.

    No OCI consulta `fields="timeCreated,timeModified"` (paginando se houver mais
    de uma página); no disco local usa o mtime do arquivo. Se um objeto existir
    nos dois, prevalece a data do OCI.
    """
    por_nome: dict[str, datetime | None] = {}
    base = (pathlib.Path(config.pasta_local()) / config.bucket()).resolve()
    if base.exists():
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base)).replace(os.sep, "/")
            if not rel.startswith(prefixo):
                continue
            try:
                por_nome[rel] = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
            except OSError:
                por_nome[rel] = None

    ns = os.getenv("OCI_NAMESPACE")
    if ns:
        try:
            cliente = _cliente_oci()
            inicio = None
            while True:
                kwargs = {"prefix": prefixo, "fields": "timeCreated,timeModified"}
                if inicio:
                    kwargs["start"] = inicio
                r = cliente.list_objects(ns, config.bucket(), **kwargs)
                if r is None:
                    break
                for o in r.data.objects:
                    if not o.name.startswith(prefixo):
                        continue
                    data = _normalizar_data(
                        getattr(o, "time_created", None)
                        or getattr(o, "time_modified", None)
                    )
                    por_nome[o.name] = data
                inicio = getattr(r.data, "next_start_with", None)
                if not inicio:
                    break
        except Exception:
            # não achou na nuvem: mantém o que veio do disco
            logger.exception("Falha ao consultar OCI; usando armazenamento local")

    return sorted(por_nome.items(), key=lambda item: item[0])


def apagar(caminho: str) -> None:
    """Remove o objeto (OCI e disco). Não falha se ele não existir."""
    _seguro(caminho)
    ns = os.getenv("OCI_NAMESPACE")
    if ns:
        try:
            _cliente_oci().delete_object(ns, config.bucket(), caminho)
        except Exception as e:
            if getattr(e, "status", None) != 404:
                raise
    local = _local(caminho)
    if local.exists():
        local.unlink()
