import pytest

from app.eventos import ServicoEventos
from app.status import StatusDocumento as S


def test_sequencia_de_status_de_rotina(tmp_path):
    ev = ServicoEventos(tmp_path)
    assert ev.status_atual("doc1") is None
    for s in (S.RECEBIDO, S.PROCESSANDO, S.PROCESSADO):
        ev.registrar("doc1", s)
    assert [e["status"] for e in ev.listar("doc1")] == [
        "recebido",
        "processando",
        "processado",
    ]
    assert ev.status_atual("doc1") == S.PROCESSADO


def test_auditoria_humana_e_ultimo_evento(tmp_path):
    ev = ServicoEventos(tmp_path)
    ev.registrar("doc2", S.PROCESSANDO)
    ev.registrar("doc2", S.EM_AUDITORIA_HUMANA)
    assert ev.status_atual("doc2") == S.EM_AUDITORIA_HUMANA


@pytest.mark.parametrize("ruim", ["../x", "a/b", "", "a b"])
def test_id_invalido_e_rejeitado(tmp_path, ruim):
    with pytest.raises(ValueError):
        ServicoEventos(tmp_path).registrar(ruim, S.RECEBIDO)


def test_listar_por_status_devolve_so_os_que_estao_nele_agora(tmp_path):
    ev = ServicoEventos(tmp_path)
    ev.registrar("a", S.RECEBIDO)
    ev.registrar("a", S.EM_AUDITORIA_HUMANA)
    ev.registrar("b", S.RECEBIDO)
    ev.registrar("b", S.EM_AUDITORIA_HUMANA)
    ev.registrar("b", S.PROCESSADO)
    (tmp_path / "quebrado.json").write_text("{x", encoding="utf-8")
    achados = ev.listar_por_status(S.EM_AUDITORIA_HUMANA)
    assert [doc for doc, _ in achados] == ["a"]
    assert achados[0][1] == ev.listar("a")[0]["em"]  # chegada = 1º evento


def test_pasta_so_e_criada_no_primeiro_registro(tmp_path):
    pasta = tmp_path / "eventos"
    ev = ServicoEventos(pasta)
    assert not pasta.exists() and ev.listar_por_status(S.RECEBIDO) == []
    ev.registrar("x", S.RECEBIDO)
    assert pasta.exists()


def test_status_do_documento_prefere_os_eventos_e_deduz_do_resultado_se_nao_houver(
    tmp_path, monkeypatch
):
    from app.eventos import servico_padrao, status_do_documento

    monkeypatch.setenv("EVENTOS_DIR", str(tmp_path))
    revisao = {"decisao_roteamento": {"destino_principal": "Fila_Revisao_Humana"}}
    farmacia = {"decisao_roteamento": {"destino_principal": "Farmacia_Hospitalar"}}
    # sem evento: deduz do resultado salvo
    assert status_do_documento("A", revisao) == "em_auditoria_humana"
    assert status_do_documento("B", farmacia) == "processado"
    assert status_do_documento("C") is None
    # com evento: o evento manda
    servico_padrao().registrar("B", S.RECEBIDO)
    assert status_do_documento("B", farmacia) == "recebido"
    assert (
        status_do_documento("../x", revisao) == "em_auditoria_humana"
    )  # id ruim não quebra
