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