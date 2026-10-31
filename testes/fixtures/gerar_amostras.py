import io

import pymupdf
from PIL import Image, ImageFilter

laudo = (
    "Paciente: Maria Teste, 45 anos.\nMedico: Dr. Joao Souza CRM 12345 SP\n"
    "Hemograma completo: hemoglobina 14,2 g/dL, leucocitos 6.300/mm3.\n"
    "Diagnostico: sem alteracoes."
)

# 1) imagem legível
# doc = pymupdf.open()
# doc.new_page().insert_text((50, 80), laudo)
# png = doc[0].get_pixmap(dpi=150).tobytes("png")
# open("amostra_legivel.png", "wb").write(png)
with pymupdf.open() as doc:
    doc.new_page().insert_text((50, 80), laudo)
    png = doc[0].get_pixmap(dpi=150).tobytes("png")

with open("amostra_legivel.png", "wb") as abrir_amostra:
    abrir_amostra.write(png)

# 2) imagem ilegível (muito borrada)
img = Image.open(io.BytesIO(png)).filter(ImageFilter.GaussianBlur(30))
img.save("amostra_borrada.png")

# 3) PDF escaneado (só imagem, sem texto selecionável)
scan = pymupdf.open()
pagina = scan.new_page()
pagina.insert_image(pagina.rect, stream=png)
scan.save("amostra_escaneada.pdf")
print("ok")
