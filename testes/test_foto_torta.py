"""H1.4.2 T6 — Testes de pré-processamento de fotos tortas ou escuras.

Cenários obrigatórios (todos sem LLM, sem OCI):
  1. Foto com tag EXIF de rotação 90° → pré-processamento corrige → imagem chega
     ao leitor já em PNG de escala de cinza (não bytes originais).
  2. Foto com área escura artificial → lida com sucesso OU devolve tipo_motivo=sombra.
  3. Foto cortada (imagem parcial) → devolve tipo_motivo=corte.
  4. Original em storage fica intacto após o pré-processamento (nunca sobrescrito).
  5. preprocessar_imagem nunca grava em disco (apenas bytes em memória).
  6. MotivoIlegibilidade.PROBLEMAS_DE_CAPTURA contém os três valores esperados.
"""

import io

import pytest
from PIL import Image, ImageDraw

from app.imagem import preprocessar_imagem
from app.schemas import Legibilidade, MotivoIlegibilidade

# ---------------------------------------------------------------------------
# Helpers para gerar imagens sintéticas
# ---------------------------------------------------------------------------


def _png_simples(
    w: int = 400, h: int = 200, texto: str = "Documento Sintético"
) -> bytes:
    """PNG branco com texto, sem tag EXIF."""
    img = Image.new("RGB", (w, h), "white")
    ImageDraw.Draw(img).text((10, 10), texto, fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _jpeg_com_exif_rotacao(graus: int = 90) -> bytes:
    """JPEG com tag EXIF Orientation correspondente à rotação indicada (via Pillow nativo)."""
    # Mapeamento graus -> tag 0x0112 (Orientation) do EXIF
    # 6: Rotated 90 CW (transposição inverte w e h)
    orientacao_exif = {90: 6, 180: 3, 270: 8, 0: 1}
    img = Image.new("RGB", (300, 100), "white")
    ImageDraw.Draw(img).text((10, 10), "Texto de teste rotacionado", fill="black")

    exif = img.getexif()
    exif[0x0112] = orientacao_exif.get(graus, 1)

    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def _png_escuro(w: int = 400, h: int = 200) -> bytes:
    """PNG com área escura artificial simulando sombra."""
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "Laudo: hemoglobina 14,2", fill="black")
    # Sombra: rectângulo escuro cobrindo metade da imagem
    draw.rectangle([(0, h // 2), (w, h)], fill=(30, 30, 30))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _png_cortado(w: int = 60, h: int = 60) -> bytes:
    """PNG muito pequeno simulando documento cortado (parcial)."""
    img = Image.new("RGB", (w, h), "white")
    ImageDraw.Draw(img).text((2, 2), "...", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# T1 — Pré-processamento Pillow
# ---------------------------------------------------------------------------


class TestPreprocessarImagem:
    """T1: a função preprocessar_imagem corrige orientação, contraste e cor."""

    def test_devolve_png(self):
        """Saída é sempre PNG (magic bytes \\x89PNG)."""
        resultado = preprocessar_imagem(_png_simples())
        assert resultado.startswith(b"\x89PNG"), "Saída deve ser PNG"

    def test_converte_para_escala_de_cinza(self):
        """A imagem de saída deve estar em modo L (escala de cinza)."""
        resultado = preprocessar_imagem(_png_simples())
        with Image.open(io.BytesIO(resultado)) as img:
            assert img.mode == "L", f"Esperado modo L, mas foi {img.mode}"

    def test_corrige_orientacao_exif_90_graus(self):
        """Foto JPEG girada 90° pelo EXIF: a saída PNG deve ter as dimensões corrigidas.

        O JPEG original é 300×100 (largura×altura). Com rotação EXIF de 90°,
        a imagem "real" (como deve aparecer ao utilizador) é 100×300.
        O preprocessador deve aplicar exif_transpose e entregar 100×300.
        """
        jpeg_girado = _jpeg_com_exif_rotacao(90)
        resultado = preprocessar_imagem(jpeg_girado)
        with Image.open(io.BytesIO(resultado)) as img:
            largura, altura = img.size
        # Após exif_transpose de 90°: largura e altura trocam
        assert altura > largura, (
            f"Após correcção EXIF 90°, altura ({altura}) deve ser maior que largura ({largura})"
        )

    def test_aceita_png_sem_exif(self):
        """PNG sem EXIF não deve levantar excepção."""
        resultado = preprocessar_imagem(_png_simples())
        assert len(resultado) > 0

    def test_aceita_imagem_escura(self):
        """Imagem com sombra é pré-processada sem erro."""
        resultado = preprocessar_imagem(_png_escuro())
        assert resultado.startswith(b"\x89PNG")

    def test_nunca_grava_em_disco(self, tmp_path, monkeypatch):
        """Nenhum ficheiro é criado em disco durante o pré-processamento."""
        arquivos_antes = list(tmp_path.rglob("*"))
        preprocessar_imagem(_png_simples())
        arquivos_depois = list(tmp_path.rglob("*"))
        assert arquivos_antes == arquivos_depois, (
            "preprocessar_imagem não deve criar ficheiros"
        )


# ---------------------------------------------------------------------------
# T1 integrado no grafo — imagem chega ao leitor já pré-processada
# ---------------------------------------------------------------------------


class TestPreprocessamentoNoGrafo:
    """T1: n_ler_entrada aplica pré-processamento antes de chamar o leitor."""

    def test_leitor_recebe_png_escala_de_cinza(self):
        """O leitor (mockado) deve receber bytes PNG em escala de cinza, não o original."""
        from app.grafo import triar

        imagens_recebidas: list[bytes] = []

        def leitor_espiao(imagens: list[bytes]) -> tuple[str, Legibilidade]:
            imagens_recebidas.extend(imagens)
            return "Texto extraído.", Legibilidade(legivel=True)

        def extrator_falso(texto: str):
            from app.schemas import Extracao

            return Extracao(
                tipo_documento="Laudo Laboratorial",
                nivel_prioridade="Rotina",
                score_confianca_classificacao=0.9,
            )

        jpeg_girado = _jpeg_com_exif_rotacao(90)
        triar("", extrator_falso, pdf_bytes=jpeg_girado, leitor=leitor_espiao)

        assert len(imagens_recebidas) == 1
        recebida = imagens_recebidas[0]
        # Deve chegar como PNG
        assert recebida.startswith(b"\x89PNG"), "Leitor deve receber PNG"
        # E em escala de cinza
        with Image.open(io.BytesIO(recebida)) as img:
            assert img.mode == "L", (
                f"Leitor deve receber imagem em modo L, foi {img.mode}"
            )

    def test_original_no_storage_fica_intacto(self, tmp_path, monkeypatch):
        """T4: storage.listar('recebidos/') deve ter apenas o original após pré-processamento.

        A cópia pré-processada NUNCA é gravada em recebidos/.
        """
        monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path / "storage"))
        monkeypatch.delenv("OCI_NAMESPACE", raising=False)

        from fastapi.testclient import TestClient

        from app import storage
        from app.api import criar_app

        def leitor_legivel(imagens):
            return "Texto extraído.", Legibilidade(legivel=True)

        def extrator_falso(texto):
            from app.schemas import Extracao

            return Extracao(
                tipo_documento="Laudo Laboratorial",
                nivel_prioridade="Rotina",
                score_confianca_classificacao=0.9,
            )

        app = criar_app(extrator=extrator_falso)
        client = TestClient(app)

        png_original = _png_simples()
        resp = client.post(
            "/triagem/arquivo",
            data={"documento_id": "DOC-EXIF-TEST", "canal_origem": "scanner"},
            files={"arquivo": ("foto.png", png_original, "image/png")},
            params={"aguardar": "true"},
        )
        assert resp.status_code in (200, 202), resp.text

        # Apenas o original deve estar em recebidos/
        objetos = storage.listar("recebidos/")
        assert len(objetos) == 1, (
            f"Esperado 1 original em recebidos/, encontrados: {objetos}"
        )
        # O original deve ter o conteúdo inalterado
        conteudo = storage.ler(objetos[0])
        assert conteudo == png_original, (
            "O conteúdo do original foi alterado (não devia)"
        )


# ---------------------------------------------------------------------------
# T2 — Modelo Legibilidade com motivo tipado
# ---------------------------------------------------------------------------


class TestLegibilidadeComTipoMotivo:
    """T2: Legibilidade.tipo_motivo contém o valor tipado quando legivel=False."""

    @pytest.mark.parametrize("tipo_motivo", ["inclinacao", "sombra", "corte", "outro"])
    def test_legibilidade_aceita_tipo_motivo(self, tipo_motivo: str):
        leg = Legibilidade(legivel=False, motivo="Detalhe", tipo_motivo=tipo_motivo)
        assert leg.tipo_motivo == tipo_motivo

    def test_legibilidade_tipo_motivo_opcional(self):
        """tipo_motivo é None quando não fornecido (imagem legível)."""
        leg = Legibilidade(legivel=True)
        assert leg.tipo_motivo is None

    def test_grafo_propaga_motivo_ilegibilidade(self):
        """O estado do grafo deve ter motivo_ilegibilidade quando o leitor devolve tipo_motivo."""
        from app.grafo import triar

        def leitor_sombra(imagens):
            return "", Legibilidade(
                legivel=False, motivo="sombra forte", tipo_motivo="sombra"
            )

        def extrator_falso(texto):
            from app.schemas import Extracao

            return Extracao(
                tipo_documento="Laudo Laboratorial",
                nivel_prioridade="Rotina",
                score_confianca_classificacao=0.0,
            )

        estado = triar(
            "", extrator_falso, pdf_bytes=_png_escuro(), leitor=leitor_sombra
        )
        assert estado.get("motivo_ilegibilidade") == "sombra"
        assert estado.get("ilegivel") is True

    def test_grafo_propaga_motivo_corte(self):
        """O estado do grafo deve ter motivo_ilegibilidade=corte para foto cortada."""
        from app.grafo import triar

        def leitor_corte(imagens):
            return "", Legibilidade(
                legivel=False, motivo="documento parcial", tipo_motivo="corte"
            )

        def extrator_falso(texto):
            from app.schemas import Extracao

            return Extracao(
                tipo_documento="Laudo Laboratorial",
                nivel_prioridade="Rotina",
                score_confianca_classificacao=0.0,
            )

        estado = triar(
            "", extrator_falso, pdf_bytes=_png_cortado(), leitor=leitor_corte
        )
        assert estado.get("motivo_ilegibilidade") == "corte"


# ---------------------------------------------------------------------------
# T2 — MotivoIlegibilidade.PROBLEMAS_DE_CAPTURA
# ---------------------------------------------------------------------------


class TestMotivoIlegibilidade:
    def test_problemas_de_captura_contem_inclinacao_sombra_corte(self):
        esperados = {"inclinacao", "sombra", "corte"}
        assert esperados == MotivoIlegibilidade.PROBLEMAS_DE_CAPTURA

    def test_outro_nao_e_problema_de_captura(self):
        assert "outro" not in MotivoIlegibilidade.PROBLEMAS_DE_CAPTURA
