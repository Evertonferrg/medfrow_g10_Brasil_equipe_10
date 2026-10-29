import io
from pypdf import PdfReader
 
MIN_CARACTERES = 20   # menos que isso = PDF provavelmente digitalizado (só imagem)
 
 
class PDFSemTexto(Exception):
    pass
 
 
def extrair_texto_pdf(conteudo: bytes) -> str:
    leitor = PdfReader(io.BytesIO(conteudo))
    paginas = [(p.extract_text() or "").strip() for p in leitor.pages]
    texto = "\n\n".join(p for p in paginas if p)
    if len(texto) < MIN_CARACTERES:
        # H1.1.2 T3: não tenta adivinhar; o grafo manda para revisão.
        # (A leitura por visão/OCR é a história H1.1.3.)
        raise PDFSemTexto("PDF sem texto selecionável (provavelmente digitalizado)")
    return texto

MAX_PAGINAS = 10

def renderizar_paginas(conteudo: bytes, dpi: int = 150, max_paginas: int = MAX_PAGINAS) -> list[bytes]:
    """T2: PDF escaneado -> uma imagem PNG por página, tudo em memória (nada vai ao bucket)."""
    import pymupdf  # PyMuPDF (o nome "fitz" está obsoleto)

    with pymupdf.open(stream=conteudo, filetype="pdf") as doc:
        return [doc[i].get_pixmap(dpi=dpi).tobytes("png")
                for i in range(min(len(doc), max_paginas))]