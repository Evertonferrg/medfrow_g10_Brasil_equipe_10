import pytest
from pydantic import ValidationError

from app.decisao import AcaoAuditora, DecisaoAuditora


def test_aprovar_so_precisa_do_nome():
    d = DecisaoAuditora(acao="aprovar", auditora="  Dra. Helena ")
    assert d.acao is AcaoAuditora.APROVAR and d.auditora == "Dra. Helena"


@pytest.mark.parametrize(
    "dados",
    [
        {"acao": "rejeitar", "auditora": "Helena"},  # sem motivo
        {"acao": "corrigir", "auditora": "Helena"},  # sem correções
        {"acao": "redirecionar", "auditora": "Helena"},  # sem destino
        {"acao": "aprovar", "auditora": ""},
        {"acao": "aprovar", "auditora": "Helena\nFalsa"},  # quebra de linha (log)
        {"acao": "apagar", "auditora": "Helena"},
    ],
)
def test_decisoes_invalidas(dados):
    with pytest.raises(ValidationError):
        DecisaoAuditora(**dados)


def test_acoes_com_campos_exigidos():
    assert (
        DecisaoAuditora(acao="rejeitar", auditora="H", motivo="ilegível").motivo
        == "ilegível"
    )
    assert DecisaoAuditora(
        acao="corrigir", auditora="H", correcoes={"crm": "123456-SP"}
    ).correcoes
    assert DecisaoAuditora(
        acao="redirecionar", auditora="H", destino="Prontuario_Eletronico"
    ).destino
