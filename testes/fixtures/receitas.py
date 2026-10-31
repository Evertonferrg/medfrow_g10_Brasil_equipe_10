"""Receitas SINTÉTICAS (nomes, CRM e dados fictícios) para os testes da H1.3.4."""

CABECALHO = (
    "RECEITUARIO. Paciente: Maria Souza, 40 anos. Dr. Paulo Lima CRM 100001 SP. "
)

AMOXICILINA = "Amoxicilina 500mg, via oral, de 8 em 8 horas por 7 dias."
DIPIRONA = "Dipirona 1g, via oral, de 6 em 6 horas se dor ou febre."
OMEPRAZOL = "Omeprazol 20mg, via oral, 1 vez ao dia por 14 dias."
IBUPROFENO = "Ibuprofeno 600mg, via oral, de 12 em 12 horas por 5 dias."
LORATADINA = "Loratadina 10mg, via oral, 1 vez ao dia por 10 dias."

RECEITA_1 = CABECALHO + f"1) {AMOXICILINA}"
RECEITA_3 = CABECALHO + f"1) {AMOXICILINA} 2) {DIPIRONA} 3) {OMEPRAZOL}"
RECEITA_5 = CABECALHO + (
    f"1) {AMOXICILINA} 2) {DIPIRONA} 3) {OMEPRAZOL} 4) {IBUPROFENO} 5) {LORATADINA}"
)
RECEITA_SEM_DOSE = CABECALHO + "1) Amoxicilina, via oral, de 8 em 8 horas por 7 dias."

# O que um extrator correto devolveria para a RECEITA_3
ITENS_RECEITA_3 = [
    {
        "nome": "Amoxicilina",
        "dose": "500mg",
        "via": "via oral",
        "frequencia": "de 8 em 8 horas",
        "duracao": "7 dias",
    },
    {
        "nome": "Dipirona",
        "dose": "1g",
        "via": "via oral",
        "frequencia": "de 6 em 6 horas",
    },
    {
        "nome": "Omeprazol",
        "dose": "20mg",
        "via": "via oral",
        "frequencia": "1 vez ao dia",
        "duracao": "14 dias",
    },
]
