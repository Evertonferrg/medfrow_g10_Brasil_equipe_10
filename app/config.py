import os
from dotenv import load_dotenv
 
load_dotenv()  # sem override: variável de ambiente real sempre vence o .env
 
 
import json
from pathlib import Path

ARQUIVO_REGRAS = Path(__file__).resolve().parents[1] / "config" / "regras.json"


def limiar_confianca() -> float:
    """Abaixo deste score o documento vai para revisão humana (H1.2.2 T2)."""
    if "LIMIAR_CONFIANCA" in os.environ:
        return float(os.environ["LIMIAR_CONFIANCA"])
    try:
        dados = json.loads(ARQUIVO_REGRAS.read_text(encoding="utf-8"))
        return float(dados.get("limite_confianca", 0.80))
    except Exception:
        return 0.80
 
 
def bucket() -> str:
    return os.getenv("OCI_BUCKET", "mediflow-documentos-clinicos")
 
 
def pasta_local() -> str:
    return os.getenv("STORAGE_LOCAL_DIR", "storage_local")
 
 
def modelo_gemini() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
 