"""H3.4.1 T3 — exibir o documento original sem JavaScript."""


def paginas_do_original(
    conteudo: bytes, content_type: str, max_paginas: int = 10, zoom: float = 1.5
) -> list[bytes]:
    """Devolve uma lista de imagens (bytes) prontas para st.image.

    - imagem: devolve o próprio arquivo;
    - PDF: renderiza cada página em PNG com o PyMuPDF (até `max_paginas`).
    """
    tipo = (content_type or "").split(";")[0].strip().lower()
    if tipo.startswith("image/"):
        return [conteudo]
    if tipo == "application/pdf":
        import pymupdf  # PyMuPDF (importado aqui para a UI abrir sem ele em outras telas)

        paginas = []
        with pymupdf.open(stream=conteudo, filetype="pdf") as pdf:
            for pagina in pdf.pages(0, min(len(pdf), max_paginas)):
                pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
                paginas.append(pix.tobytes("png"))
        return paginas
    raise ValueError(f"Tipo de arquivo não suportado para visualização: {tipo or 'desconhecido'}")


def mostrar_original(st, conteudo: bytes, content_type: str) -> None:
    tipo = (content_type or "").split(";")[0].strip().lower()
    if tipo == "text/plain":
        st.text(conteudo.decode("utf-8", errors="replace"))
        return
    try:
        paginas = paginas_do_original(conteudo, content_type)
    except ValueError as erro:
        st.warning(str(erro))
        return
    for png in paginas:
        st.image(png)