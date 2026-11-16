"""H1.4.2 T1 — Pré-processamento de imagens tortas ou escuras.

Aplica, em memória, três filtros antes de enviar a imagem ao LLM:
  1. exif_transpose  — corrige orientação registrada na câmera (rotação EXIF).
  2. autocontrast    — melhora contraste sem clipar destaques.
  3. convert("L")    — converte para escala de cinza, reduzindo ruído de cor.

A cópia tratada NUNCA é gravada em recebidos/; é usada apenas em memória e
descartada após a leitura pelo LLM.  O original permanece intacto no storage
(T4: ServicoArmazenamento já recusa sobrescrever via ObjetoJaExisteError).
"""

import io

from PIL import Image, ImageOps


def preprocessar_imagem(dados: bytes) -> bytes:
    """Devolve uma cópia PNG tratada (orientação + contraste + cinza), em memória.

    Parâmetros
    ----------
    dados:
        Bytes brutos de uma imagem (JPEG, PNG ou qualquer formato que Pillow suporte).

    Retorno
    -------
    bytes
        PNG em escala de cinza, com orientação e contraste corrigidos.
        O formato de saída é sempre PNG para evitar artefatos de recompressão JPEG.
    """
    with Image.open(io.BytesIO(dados)) as img:
        # 1. Corrige rotação registrada no EXIF (foto tirada em modo retrato/paisagem)
        img = ImageOps.exif_transpose(img)
        # 2. Converte para RGB antes do autocontraste (evita erros em RGBA/P)
        if img.mode not in ("L", "RGB"):
            img = img.convert("RGB")
        # 3. Autocontraste — estira o histograma sem clipar os extremos
        img = ImageOps.autocontrast(img, cutoff=0)
        # 4. Escala de cinza — reduz ruído de cor e tamanho do payload para o LLM
        img = img.convert("L")

        saida = io.BytesIO()
        img.save(saida, format="PNG", optimize=True)
        return saida.getvalue()
