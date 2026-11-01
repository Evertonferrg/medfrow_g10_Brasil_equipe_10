"""H2.3.1 T5 — protege o contrato do ResultadoTriagem.

O snapshot do schema fica em testes/fixtures/resultado_triagem.schema.json.
Para criá-lo (ou atualizá-lo de propósito, depois de mudar o contrato):

    PowerShell:  $env:ATUALIZAR_SNAPSHOT = "1"; pytest testes/test_contrato.py; Remove-Item Env:ATUALIZAR_SNAPSHOT
"""

import json
import os
from pathlib import Path

from app import resposta, storage
from app.grafo import triar
from app.schemas import ResultadoTriagem
from testes.conftest import LAUDO_TEP, cliente_com, extracao, extrator_fixo

SNAPSHOT = Path(__file__).parent / "fixtures" / "resultado_triagem.schema.json"

# Exemplo no formato do edital. Se o JSON do edital tiver outro detalhe, cole-o aqui.
EXEMPLO_EDITAL = {
    "status": "processado",
    "documento_id": "DOC-CLIN-2026-8942",
    "classificacao": {
        "tipo_documento": "Laudo de Exame de Imagem",
        "especialidade": "Radiologia / Pneumologia",
        "nivel_prioridade": "Urgente",
        "score_confianca_classificacao": 0.95,
    },
    "dados_extraidos": {
        "paciente": {
            "nome": "Carlos Eduardo Mendes",
            "idade": 52,
            "data_nascimento": None,
        },
        "medico_solicitante": {"nome": "Dra. Renata Silveira", "crm": "145892-SP"},
        "diagnostico_principal": "Tromboembolismo Pulmonar Agudo (TEP)",
        "cid_sugerido": "I26.9",
    },
    "problemas": [],
    "decisao_roteamento": {
        "destino_principal": "Fila_Emergencia_Medica",
        "requer_auditoria_humana": False,
        "justificativa_roteamento": "Laudo com prioridade Urgente.",
        "regra_aplicada": "R-URGENCIA",
        "notificacao_gerada": {
            "canal": "Alerta_Plantao_Medico",
            "mensagem": "ALERTA URGENTE: TEP paciente Carlos Eduardo Mendes.",
        },
    },
    "armazenamento_oci": {
        "bucket": "mediflow-documentos-clinicos",
        "caminho_objeto": "processados/urgentes/DOC-CLIN-2026-8942.json",
        "status_backup": "sucesso",
        "local": "disco",
        "urgente": True,
    },
}


def test_json_de_exemplo_do_edital_e_lido_sem_erro():
    r = ResultadoTriagem.model_validate(EXEMPLO_EDITAL)
    assert r.decisao_roteamento.destino_principal == "Fila_Emergencia_Medica"
    assert r.armazenamento_oci is not None
    assert r.armazenamento_oci.urgente is True
    assert r.model_dump(mode="json")["classificacao"] == EXEMPLO_EDITAL["classificacao"]


def test_snapshot_do_schema_acusa_mudanca_acidental():
    atual = json.loads(json.dumps(ResultadoTriagem.model_json_schema()))
    if os.getenv("ATUALIZAR_SNAPSHOT") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(
            json.dumps(atual, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return
    assert SNAPSHOT.exists(), (
        "snapshot ausente: rode uma vez com ATUALIZAR_SNAPSHOT=1 e faça commit do arquivo"
    )
    assert json.loads(SNAPSHOT.read_text(encoding="utf-8")) == atual, (
        "O contrato do ResultadoTriagem mudou. Se foi de propósito, atualize o snapshot "
        "(ATUALIZAR_SNAPSHOT=1) e avise quem consome a API."
    )


def test_resposta_da_api_cabe_no_contrato(cliente):
    corpo = {
        "documento_id": "DOC-CON-001",
        "tipo_arquivo": "TEXTO",
        "documento_texto": LAUDO_TEP,
        "canal_origem": "Pronto_Socorro",
    }
    post = cliente.post("/triagem?aguardar=true", json=corpo).json()
    get = cliente.get("/documentos/DOC-CON-001").json()
    for j in (post, get):
        r = ResultadoTriagem.model_validate(j)
        assert (
            r.classificacao
            and r.dados_extraidos
            and r.decisao_roteamento
            and r.armazenamento_oci
        )


# ---- critério 2: fora do formato nunca é entregue ----
def classificador_quebrado(extracao_, score):
    return {
        "tipo_documento": "categoria-que-nao-existe"
    }  # não passa pelo modelo Classificacao


def test_resultado_fora_do_formato_vai_para_revisao_sem_resposta_parcial():
    estado = triar(
        LAUDO_TEP,
        extrator_fixo(extracao()),
        classificador=classificador_quebrado,
        documento_id="DOC-CON-002",
    )
    assert estado["destino"] == "Fila_Revisao_Humana"
    assert estado["motivo_revisao"] == "falha de processamento"
    r = ResultadoTriagem.model_validate(estado["resultado"])
    assert r.status == "erro_processamento"
    assert r.classificacao is None and r.dados_extraidos is None  # nada parcial
    assert r.decisao_roteamento.requer_auditoria_humana is True
    assert "falha de processamento" in r.decisao_roteamento.justificativa_roteamento


def test_resultado_fora_do_formato_e_arquivado_na_auditoria_humana():
    estado = triar(
        LAUDO_TEP,
        extrator_fixo(extracao()),
        classificador=classificador_quebrado,
        documento_id="DOC-CON-003",
    )
    saida = resposta.arquivar("DOC-CON-003", estado)
    assert saida["status"] == "erro_processamento"
    assert (
        saida["armazenamento_oci"]["caminho_objeto"]
        == "auditoria_humana/DOC-CON-003.json"
    )
    assert storage.existe("auditoria_humana/DOC-CON-003.json")


def test_fakellm_com_saida_quebrada_vai_para_revisao_com_falha_de_processamento():
    c = cliente_com(lambda texto: {"isto": "nao e uma Extracao"})
    corpo = {
        "documento_id": "DOC-CON-004",
        "tipo_arquivo": "TEXTO",
        "documento_texto": LAUDO_TEP,
        "canal_origem": "Pronto_Socorro",
    }
    j = c.post("/triagem?aguardar=true", json=corpo).json()
    assert j["decisao_roteamento"]["destino_principal"] == "Fila_Revisao_Humana"
    assert (
        "falha de processamento"
        in j["decisao_roteamento"]["justificativa_roteamento"].lower()
    )
