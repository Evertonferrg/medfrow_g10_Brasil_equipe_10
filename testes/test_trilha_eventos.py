import json
from types import SimpleNamespace

import pytest

from app.eventos import ServicoEventos, registrar_desfecho
from app.status import StatusDocumento as S


def test_decisao_automatica_registra_agente_regra_e_horario(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path))
    resultado = SimpleNamespace(
        decisao_roteamento=SimpleNamespace(
            destino_principal="Farmacia_Hospitalar", regra_aplicada="R-RECEITA"
        )
    )
    registrar_desfecho("D1", resultado)
    (ev,) = ServicoEventos(tmp_path).listar("D1")
    assert ev["autor_tipo"] == "agente" and ev["regra_aplicada"] == "R-RECEITA"
    assert ev["status"] == "processado" and ev["em"]


def test_correcao_registra_nome_valor_anterior_e_novo(tmp_path):
    ev = ServicoEventos(tmp_path)
    reg = ev.registrar_decisao(
        "D2",
        S.EM_AUDITORIA_HUMANA,
        autor_tipo="auditora",
        autor_nome="Helena",
        campo="crm",
        valor_anterior="12345-XX",
        valor_novo="CRM-SP 123456",
    )
    assert (reg["autor_nome"], reg["valor_anterior"], reg["valor_novo"]) == (
        "Helena",
        "12345-XX",
        "CRM-SP 123456",
    )


def test_autor_invalido_e_recusado(tmp_path):
    with pytest.raises(ValueError):
        ServicoEventos(tmp_path).registrar_decisao(
            "D3", S.PROCESSADO, autor_tipo="robo", autor_nome="x"
        )


def test_cadeia_integra_e_alteracao_a_mao_quebra_a_verificacao(tmp_path):
    ev = ServicoEventos(tmp_path)
    ev.registrar("D4", S.RECEBIDO)
    ev.registrar_decisao(
        "D4",
        S.EM_AUDITORIA_HUMANA,
        autor_tipo="agente",
        autor_nome="agente",
        regra_aplicada="R-REVISAO",
    )
    ev.registrar_decisao(
        "D4",
        S.PROCESSADO,
        autor_tipo="auditora",
        autor_nome="Helena",
        campo="crm",
        valor_anterior="a",
        valor_novo="b",
    )
    assert ev.verificar_cadeia("D4") == []
    caminho = tmp_path / "D4.json"
    eventos = json.loads(caminho.read_text(encoding="utf-8"))
    eventos[2]["valor_novo"] = "outro"  # adultera um valor
    caminho.write_text(json.dumps(eventos), encoding="utf-8")
    assert any("alterado" in p for p in ev.verificar_cadeia("D4"))


def test_remover_evento_do_meio_quebra_o_encadeamento(tmp_path):
    ev = ServicoEventos(tmp_path)
    for s in (S.RECEBIDO, S.PROCESSANDO, S.PROCESSADO):
        ev.registrar("D5", s)
    caminho = tmp_path / "D5.json"
    eventos = json.loads(caminho.read_text(encoding="utf-8"))
    del eventos[1]
    caminho.write_text(json.dumps(eventos), encoding="utf-8")
    assert any("não encadeia" in p for p in ev.verificar_cadeia("D5"))


def test_eventos_antigos_sem_hash_sao_aceitos_so_no_comeco(tmp_path):
    caminho = tmp_path / "D6.json"
    caminho.write_text(
        json.dumps([{"status": "recebido", "em": "2026-11-01T00:00:00+00:00"}]),
        encoding="utf-8",
    )
    ev = ServicoEventos(tmp_path)
    assert ev.verificar_cadeia("D6") == []
    ev.registrar("D6", S.PROCESSADO)
    assert ev.verificar_cadeia("D6") == []


def test_correcao_de_campo_vazio_registra_valor_anterior_nulo(tmp_path):
    ev = ServicoEventos(tmp_path)
    reg = ev.registrar_decisao(
        "D7",
        S.EM_AUDITORIA_HUMANA,
        autor_tipo="auditora",
        autor_nome="Helena",
        campo="crm",
        valor_anterior=None,
        valor_novo="CRM-SP 123456",
    )
    assert "valor_anterior" in reg and reg["valor_anterior"] is None
    assert ev.verificar_cadeia("D7") == []
    # sem campo, valores nulos continuam sendo omitidos
    outro = ev.registrar_decisao(
        "D8", S.PROCESSADO, autor_tipo="agente", autor_nome="agente"
    )
    assert "valor_anterior" not in outro
