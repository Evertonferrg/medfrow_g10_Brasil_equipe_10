import os
from dotenv import load_dotenv
 
load_dotenv()  # sem override: variável de ambiente real sempre vence o .env
 
 
def limiar_confianca() -> float:
    """Abaixo deste score o documento vai para revisão humana (H1.2.2 T2)."""
    return float(os.getenv("LIMIAR_CONFIANCA", "0.75"))
 
 
def bucket() -> str:
    return os.getenv("OCI_BUCKET", "mediflow-documentos-clinicos")
 
 
def pasta_local() -> str:
    return os.getenv("STORAGE_LOCAL_DIR", "storage_local")
 
 
def modelo_gemini() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
 