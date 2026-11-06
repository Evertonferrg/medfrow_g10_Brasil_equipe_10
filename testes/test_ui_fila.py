from datetime import UTC, datetime, timedelta

from ui.componentes.fila import minutos_de_espera, texto_dose_destacada, texto_espera


def test_minutos_de_espera():
    agora = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
    assert minutos_de_espera((agora - timedelta(minutes=45)).isoformat(), agora) == 45
    assert minutos_de_espera((agora + timedelta(minutes=5)).isoformat(), agora) == 0


def test_texto_espera_e_destaque_com_texto():
    assert texto_espera(75) == "1 h 15 min" and texto_espera(8) == "8 min"
    assert "FORA DA FAIXA" in texto_dose_destacada(
        {"medicamento": "Morfina", "dose": "500 mg"}
    )
