import re
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

# enum + submodelo de classificação e destino moram em app/modelos/ (fonte única
# das categorias); são reexportados aqui para manter os imports antigos.
from .modelos import (  # noqa: F401
    Classificacao,
    Prioridade,
    TipoDocumento,
    TipoDocumentoLiteral,
    Destino,
    DestinoLiteral,
    DecisaoRoteamento,
    Notificacao,
)

 
# ---------- ENTRADA (H1.1.1 T1) ----------
ID_REGEX = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,63}")
CANAL_REGEX = re.compile(r"[\w-]{1,50}")
MAX_TEXTO = 200_000   # caracteres: limita o tamanho do que a API aceita (proteção contra abuso)


def validar_id(valor: str) -> str:
    """O ID vira nome de arquivo/objeto: só letras, números, _ e -.
    Isso fecha o buraco de 'path traversal' (ex.: ../../x)."""
    valor = (valor or "").strip()
    if not ID_REGEX.fullmatch(valor):
        raise ValueError("documento_id inválido: use 3 a 64 letras, números, _ ou -")
    return valor


class DocumentoEntrada(BaseModel):
    documento_id: str
    tipo_arquivo: str = "TEXTO"
    documento_texto: str
    canal_origem: str

    @field_validator("documento_id")
    @classmethod
    def _id(cls, v):
        return validar_id(v)

    @field_validator("documento_texto")
    @classmethod
    def _texto(cls, v):
        if not v or not v.strip():
            raise ValueError("documento vazio")
        if len(v) > MAX_TEXTO:
            raise ValueError(f"documento acima de {MAX_TEXTO} caracteres")
        return v

    @field_validator("canal_origem")
    @classmethod
    def _canal(cls, v):
        v = (v or "").strip()
        if not CANAL_REGEX.fullmatch(v):
            raise ValueError("canal_origem inválido")
        return v






class Paciente(BaseModel):
    nome: Optional[str] = None
    idade: Optional[int] = None
    data_nascimento: Optional[str] = None   # preservada como está (H1.3.1)


class Medico(BaseModel):
    nome: Optional[str] = None
    crm: Optional[str] = None


class Medicamento(BaseModel):               # H1.3.4 T1
    nome: str
    dose: Optional[str] = None
    frequencia: Optional[str] = None
    duracao: Optional[str] = None


class Exame(BaseModel):                     # H1.3.5 T1
    nome: str
    codigo_tuss: Optional[str] = None


class Evidencia(BaseModel):                 # H1.3.6 T1
    campo: str
    trecho: str


class Extracao(BaseModel):
    tipo_documento: TipoDocumentoLiteral
    especialidade: Optional[str] = None
    nivel_prioridade: Prioridade
    score_confianca_classificacao: float = Field(ge=0, le=1)
    paciente: Paciente = Field(default_factory=Paciente)
    medico_solicitante: Medico = Field(default_factory=Medico)
    diagnostico_principal: Optional[str] = None
    cid_sugerido: Optional[str] = None
    cid_origem: Optional[str] = None        # "documento" ou "sugerido" (preenchido na validação)
    medicamentos: List[Medicamento] = Field(default_factory=list)
    exames: List[Exame] = Field(default_factory=list)
    evidencias: List[Evidencia] = Field(default_factory=list)
    inconsistencias: List[str] = Field(default_factory=list)
 
 



class ArmazenamentoOCI(BaseModel):          # H5.1.2 T1
    bucket: str
    caminho_objeto: str
    status_backup: str
    local: str
    urgente: bool


class ResultadoTriagem(BaseModel):
    status: str
    documento_id: str
    classificacao: Optional[Classificacao] = None
    dados_extraidos: Optional[dict] = None
    problemas: List[str] = Field(default_factory=list)
    decisao_roteamento: DecisaoRoteamento
    armazenamento_oci: Optional[ArmazenamentoOCI] = None
