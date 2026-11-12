# 🧪 Guia de Testes — H2.1.3 — Enviar laudos, altas e atestados ao Prontuário

Este guia descreve como testar e validar a história **H2.1.3** no **MediFlow**:
- Laudos de exame (imagem e laboratorial) de rotina → `Prontuario_Eletronico`
- Relatórios de alta → `Prontuario_Eletronico`
- Atestados médicos → `Prontuario_Eletronico`
- Laudos **urgentes** → `Fila_Emergencia_Medica` (precedência de urgência mantida)

---

## 1. Testes Automatizados (`pytest`)

Os testes usam FakeLLM e diretório temporário isolado — **não exigem `GEMINI_API_KEY`**.

```bash
# Rodar apenas os 45 testes do H2.1.3
.venv/bin/pytest -v testes/test_roteamento_prontuario.py

# Rodar todos os testes de roteamento (H2.1.1 + H2.1.2 + H2.1.3)
.venv/bin/pytest -v testes/test_roteamento_receita.py testes/test_roteamento_guia.py testes/test_roteamento_prontuario.py

# Rodar TODA a suite (excluindo LLM e pymupdf)
.venv/bin/pytest -m "not llm" -k "not pymupdf and not pdf_apenas_imagem and not pdf_sem_texto and not pdf_escaneado" --tb=short
```

---

## 2. Subir o Projeto nos Containers (API + Interface)

```bash
# 1. Construir a imagem
podman build --build-arg PYTHON_VERSION=3.13 -t mediflow-agent:dev .

# 2. Subir a API FastAPI na porta 8000
podman run -d --replace --name mediflow-api --network host mediflow-agent:dev

# 3. Subir a interface Streamlit na porta 8501
podman run -d --replace --name mediflow-ui --network host \
  -e API_URL=http://localhost:8000 \
  --entrypoint streamlit mediflow-agent:dev \
  run ui/Home.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
```

Verifique se estão ativos:
```bash
curl -s http://localhost:8000/health
# Resposta esperada: {"status":"ok"}
```

---

## 3. Popular Cenários de Demonstração (Sem `GEMINI_API_KEY`)

Execute os comandos abaixo para gravar **5 documentos sintéticos de teste** dentro do container `mediflow-api`:

```bash
podman exec mediflow-api python3 -c "
from app.servico import processar
from app.schemas import Medico, Paciente, Extracao
from testes.conftest import extrator_fixo

# === CENÁRIO 1: Laudo de Exame de Imagem — Rotina (→ Prontuario_Eletronico) ===
ext_laudo_rotina = Extracao(
    tipo_documento='Laudo de Exame de Imagem',
    especialidade='Radiologia / Pneumologia',
    nivel_prioridade='Rotina',
    score_confianca_classificacao=0.95,
    paciente=Paciente(nome='Carlos Eduardo Mendes', idade=52),
    medico_solicitante=Medico(nome='Dra. Renata Silveira', crm='CRM-SP 145892'),
    diagnostico_principal='Tosse persistente sem achados tomográficos significativos',
    cid_sugerido='R05',
)
with open('storage_local/mediflow-documentos-clinicos/recebidos/DOC-LAUDO-ROTINA.txt') as f:
    texto_laudo_rotina = f.read()
processar('DOC-LAUDO-ROTINA', texto_laudo_rotina, None, extrator_fixo(ext_laudo_rotina))

# === CENÁRIO 2: Laudo de Exame de Imagem — URGENTE (→ Fila_Emergencia_Medica) ===
ext_laudo_urgente = Extracao(
    tipo_documento='Laudo de Exame de Imagem',
    especialidade='Radiologia / Pneumologia',
    nivel_prioridade='Urgente',
    score_confianca_classificacao=0.95,
    paciente=Paciente(nome='Carlos Eduardo Mendes', idade=52),
    medico_solicitante=Medico(nome='Dra. Renata Silveira', crm='CRM-SP 145892'),
    diagnostico_principal='Tromboembolismo Pulmonar Agudo (TEP)',
    cid_sugerido='I26.9',
)
with open('storage_local/mediflow-documentos-clinicos/recebidos/DOC-LAUDO-URGENTE.txt') as f:
    texto_laudo_urgente = f.read()
processar('DOC-LAUDO-URGENTE', texto_laudo_urgente, None, extrator_fixo(ext_laudo_urgente))

# === CENÁRIO 3: Relatório de Alta (→ Prontuario_Eletronico) ===
ext_alta = Extracao(
    tipo_documento='Relatório de Alta',
    especialidade='Clínica Médica / Infectologia',
    nivel_prioridade='Rotina',
    score_confianca_classificacao=0.92,
    paciente=Paciente(nome='Ana Beatriz Costa', idade=38),
    medico_solicitante=Medico(nome='Dr. Ricardo Monteiro', crm='CRM-RJ 201455'),
    diagnostico_principal='Pneumonia bacteriana comunitária',
    cid_sugerido='J18.9',
)
with open('storage_local/mediflow-documentos-clinicos/recebidos/DOC-ALTA-ROTINA.txt') as f:
    texto_alta = f.read()
processar('DOC-ALTA-ROTINA', texto_alta, None, extrator_fixo(ext_alta))

# === CENÁRIO 4: Atestado Médico (→ Prontuario_Eletronico) ===
ext_atestado = Extracao(
    tipo_documento='Atestado Médico',
    especialidade='Clínica Médica / Infectologia',
    nivel_prioridade='Rotina',
    score_confianca_classificacao=0.94,
    paciente=Paciente(nome='Ana Beatriz Costa', idade=38),
    medico_solicitante=Medico(nome='Dr. Ricardo Monteiro', crm='CRM-RJ 201455'),
    diagnostico_principal='Pneumonia bacteriana comunitária',
    cid_sugerido='J18.9',
)
with open('storage_local/mediflow-documentos-clinicos/recebidos/DOC-ATESTADO-ROTINA.txt') as f:
    texto_atestado = f.read()
processar('DOC-ATESTADO-ROTINA', texto_atestado, None, extrator_fixo(ext_atestado))

# === CENÁRIO 5: Laudo Laboratorial (→ Prontuario_Eletronico) ===
ext_lab = Extracao(
    tipo_documento='Laudo Laboratorial',
    especialidade='Clínica Médica / Infectologia',
    nivel_prioridade='Rotina',
    score_confianca_classificacao=0.93,
    paciente=Paciente(nome='Ana Beatriz Costa', idade=38),
    medico_solicitante=Medico(nome='Dr. Ricardo Monteiro', crm='CRM-RJ 201455'),
    diagnostico_principal='Pneumonia bacteriana comunitária',
    cid_sugerido='J18.9',
)
with open('storage_local/mediflow-documentos-clinicos/recebidos/DOC-LAUDO-LAB-ROTINA.txt') as f:
    texto_lab = f.read()
processar('DOC-LAUDO-LAB-ROTINA', texto_lab, None, extrator_fixo(ext_lab))

print('✅ 5 documentos de teste gravados com sucesso!')
"
```

---

## 4. Testar na Interface Visual (`http://localhost:8501`)

1. Abra **`http://localhost:8501`** no navegador.
2. No menu lateral, clique em **Resultado**.
3. Pesquise cada ID abaixo e confira os critérios de aceite:

| ID do Documento | Tipo | Resultado Esperado |
| :--- | :--- | :--- |
| **`DOC-LAUDO-ROTINA`** | Laudo de Exame de Imagem (Rotina) | • **Destino:** `Prontuario_Eletronico`<br>• **Regra:** `R-PRONTUARIO`<br>• **Diagnóstico:** Tosse persistente, CID R05<br>• **Médico:** Dra. Renata Silveira, CRM `145892-SP` |
| **`DOC-LAUDO-URGENTE`** | Laudo de Exame de Imagem (**Urgente**) | • **Destino:** `Fila_Emergencia_Medica` ⚠️<br>• **Regra:** `R-URGENCIA`<br>• **Diagnóstico:** TEP, CID I26.9<br>• Valida que **urgência tem precedência** sobre tipo |
| **`DOC-ALTA-ROTINA`** | Relatório de Alta (Rotina) | • **Destino:** `Prontuario_Eletronico`<br>• **Regra:** `R-PRONTUARIO`<br>• **Diagnóstico:** Pneumonia, CID J18.9<br>• **Médico:** Dr. Ricardo Monteiro, CRM `201455-RJ` |
| **`DOC-ATESTADO-ROTINA`** | Atestado Médico (Rotina) | • **Destino:** `Prontuario_Eletronico`<br>• **Regra:** `R-PRONTUARIO`<br>• **Diagnóstico:** Pneumonia, CID J18.9<br>• **Médico:** Dr. Ricardo Monteiro, CRM `201455-RJ` |
| **`DOC-LAUDO-LAB-ROTINA`** | Laudo Laboratorial (Rotina) | • **Destino:** `Prontuario_Eletronico`<br>• **Regra:** `R-PRONTUARIO`<br>• **Diagnóstico:** Pneumonia, CID J18.9<br>• **Médico:** Dr. Ricardo Monteiro, CRM `201455-RJ` |

---

## 5. Testar via API REST (`curl` ou Swagger)

Documentação interativa: **`http://localhost:8000/docs`**

```bash
# 1. Laudo de rotina → Prontuario_Eletronico
curl -s http://localhost:8000/documentos/DOC-LAUDO-ROTINA | python3 -m json.tool

# 2. Laudo urgente → Fila_Emergencia_Medica (precedência de urgência)
curl -s http://localhost:8000/documentos/DOC-LAUDO-URGENTE | python3 -m json.tool

# 3. Relatório de alta → Prontuario_Eletronico
curl -s http://localhost:8000/documentos/DOC-ALTA-ROTINA | python3 -m json.tool

# 4. Atestado médico → Prontuario_Eletronico
curl -s http://localhost:8000/documentos/DOC-ATESTADO-ROTINA | python3 -m json.tool

# 5. Laudo laboratorial → Prontuario_Eletronico
curl -s http://localhost:8000/documentos/DOC-LAUDO-LAB-ROTINA | python3 -m json.tool
```

---

## 6. Checklist dos Critérios de Aceite

| # | Critério | Como verificar |
| :--- | :--- | :--- |
| **CA1** | Laudo sem achado crítico → `Prontuario_Eletronico` | `DOC-LAUDO-ROTINA` e `DOC-LAUDO-LAB-ROTINA`: destino = `Prontuario_Eletronico` |
| **CA2** | Relatório de alta → `Prontuario_Eletronico` | `DOC-ALTA-ROTINA`: destino = `Prontuario_Eletronico` |
| **CA3** | Atestado médico → `Prontuario_Eletronico` | `DOC-ATESTADO-ROTINA`: destino = `Prontuario_Eletronico` |
| **CA4** | Laudo urgente **não** vai para Prontuário | `DOC-LAUDO-URGENTE`: destino = `Fila_Emergencia_Medica`, regra = `R-URGENCIA` |
| **CA5** | Precedência: urgência > tipo | Mesmo documento, mudando prioridade para Urgente, muda o destino |

---

## Documentos de Teste Criados

Os 5 documentos `.txt` estão em:
```
storage_local/mediflow-documentos-clinicos/recebidos/
├── DOC-LAUDO-ROTINA.txt      ← Laudo de imagem, rotina
├── DOC-LAUDO-URGENTE.txt      ← Laudo de imagem, URGENTE (TEP)
├── DOC-LAUDO-LAB-ROTINA.txt   ← Laudo laboratorial, rotina
├── DOC-ALTA-ROTINA.txt        ← Relatório de alta hospitalar
└── DOC-ATESTADO-ROTINA.txt    ← Atestado médico
```

