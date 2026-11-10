from app.estado_revisao import montar_estado_revisao, salvar_estado_revisao


class Modelo:
    def __init__(self, **kw):
        self.kw = kw

    def model_dump(self, mode="python"):
        return dict(self.kw)


class Mem:
    def __init__(self):
        self.salvos = {}

    def salvar(self, caminho, conteudo):
        self.salvos[caminho] = conteudo


def estado():
    return {
        "destino_calculado": "Farmacia_Hospitalar",
        "limite_confianca": 0.8,
        "extracao": Modelo(paciente={"nome": "M"}),
        "classificacao": Modelo(tipo_documento="Receituário Médico"),
        "texto": "texto do documento (não deve ser guardado)",
    }


def test_estado_guarda_so_o_necessario():
    out = montar_estado_revisao(estado())
    assert set(out) == {
        "destino_calculado",
        "limite_confianca",
        "extracao",
        "classificacao",
    }
    assert out["extracao"] == {"paciente": {"nome": "M"}}


def test_salvar_grava_ao_lado_do_resultado_e_tolera_falha():
    mem = Mem()
    salvar_estado_revisao("D1", estado(), mem)
    assert "auditoria_humana/D1.estado.json" in mem.salvos

    class Quebrado:
        def salvar(self, *a):
            raise OSError("disco cheio")

    salvar_estado_revisao("D2", estado(), Quebrado())  # não levanta


def test_estado_sem_extracao_vira_none():
    out = montar_estado_revisao({"extracao": None, "classificacao": None})
    assert out["extracao"] is None and out["destino_calculado"] is None
