ASSINATURAS = (
    (b"%PDF", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
)


def extensao_por_assinatura(conteudo: bytes) -> str | None:
    """Descobre o tipo pelos primeiros bytes (não confia no nome nem no MIME do cliente)."""
    for assinatura, extensao in ASSINATURAS:
        if conteudo.startswith(assinatura):
            return extensao
    return None
