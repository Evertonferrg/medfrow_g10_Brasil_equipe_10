"""H5.1.3 T4 — onde um documento aparece: python -m app.manutencao DOC-1

Sai com código 0 se o ID existe em exatamente um prefixo, e 1 caso contrário.
"""

import re
import sys

from app import storage
from app.revisao import prefixos_do_documento

ID_LIMPO = re.compile(r"^[A-Za-z0-9_-]+$")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or not ID_LIMPO.fullmatch(args[0]):
        print("uso: python -m app.manutencao <documento_id>")
        return 2
    achados = prefixos_do_documento(storage, args[0])
    print(f"{args[0]}: {', '.join(achados) if achados else 'não encontrado'}")
    return 0 if len(achados) == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
