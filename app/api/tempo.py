import logging
import re
import time

logger = logging.getLogger("mediflow.requisicoes")
LIMITE_MS = 2000
_NAO_IMPRIMIVEL = re.compile(r"[^\x20-\x7E]")


def limpar(caminho: str) -> str:
    """Troca caracteres de controle e não ASCII (evita 'injeção de log' com \\n)."""
    return _NAO_IMPRIMIVEL.sub("?", caminho)[:200]


def configurar_log() -> None:
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(h)


class MedirTempoMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        inicio = time.perf_counter()
        registrado = False

        def registrar(status: int) -> None:
            nonlocal registrado
            if registrado:
                return
            registrado = True
            duracao_ms = (time.perf_counter() - inicio) * 1000
            nivel = logging.WARNING if duracao_ms > LIMITE_MS else logging.INFO
            caminho = limpar(scope.get("path", ""))
            logger.log(
                nivel, "%s %s -> %s em %.1f ms", scope.get("method", "?"), caminho, status,
                duracao_ms,
                extra={"metodo": scope.get("method", "?"), "caminho": caminho,
                       "status_http": status, "duracao_ms": duracao_ms},
            )

        async def enviar(message):
            if message["type"] == "http.response.start":
                registrar(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            registrar(500)
            raise