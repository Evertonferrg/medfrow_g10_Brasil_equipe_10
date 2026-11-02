# Guia do Nosso Makefile

O Nosso Makefile reúne os comandos do dia a dia do MediFlow: rodar a aplicação, travar dependências e validar o código antes de subir para o repositório.

Para ver a lista de comandos a qualquer momento:

```bash
make help
```

---

## Pré-requisitos

| Ferramenta | Para quê |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Gerenciar dependências e rodar Python |
| Podman **ou** Docker | Construir a imagem do container |
| [Trivy](https://trivy.dev/) | Escanear a imagem e o Dockerfile |
| `make` | Executar os comandos deste guia |

O Makefile usa o Podman se ele estiver instalado. Caso contrário, usa o Docker. Para forçar um deles:

```bash
make build ENGINE=docker
```

---

## Fluxo de trabalho

### 1. Rodar a aplicação localmente

```bash
make dev
```

Sobe a API e o frontend ao mesmo tempo:

- API (FastAPI): http://localhost:8000
- Frontend (Streamlit): http://localhost:8501

A API reinicia sozinha quando você salva um arquivo. Para encerrar os dois, use `Ctrl+C`.

Se quiser subir só uma das partes:

```bash
make api   # só a API
make ui    # só o Streamlit
```

### 2. Adicionar ou atualizar uma dependência

1. Edite o arquivo `requirements.in`. Coloque só o nome do pacote, e a versão se for necessário.
2. Gere o arquivo travado:

   ```bash
   make lock
   ```

3. Faça commit dos **dois** arquivos: `requirements.in` e `requirements.txt`.

> **Não edite o `requirements.txt` à mão.** Ele é gerado com o hash de cada pacote, para que o container instale exatamente as versões verificadas. As dependências são resolvidas para o Linux do container, então o resultado é o mesmo em qualquer sistema operacional.

### 3. Antes de todo `git push`

```bash
make ci-local
```

Roda localmente as mesmas verificações da pipeline, nesta ordem, e para na primeira que falhar:

| Etapa | Comando isolado | O que verifica |
|---|---|---|
| Lint | `make lint` | Erros de código e formatação (ruff) |
| Testes | `make test` | Testes unitários (pytest) |
| Build | `make build` | Se a imagem do container é construída |
| Scan | `make scan` | Vulnerabilidades, segredos e problemas no Dockerfile (Trivy) |

Se tudo passar, pode subir. Se algo falhar, veja a próxima seção.

### 4. Depois do push: limpeza do Podman
 
Cada `make ci-local` constrói uma imagem nova. As versões anteriores ficam para trás sem nome e, com o tempo, ocupam vários GB de disco.
 
**Veja quanto espaço está em uso:**
 
```bash
podman system df
```
 
**Limpeza do dia a dia.** Remove a imagem do projeto e as imagens sem nome que sobraram dos builds anteriores:
 
```bash
podman image rm mediflow-agent:dev
podman image prune -f
```
 
**Limpeza completa.** Use quando o disco estiver apertado:
 
```bash
podman system prune -a -f
```
 
> ⚠️ O `system prune -a` apaga **todas** as imagens que não estão em uso por um container, inclusive as de outros projetos e as imagens base. O próximo build vai baixar tudo de novo e demorar mais. Volumes não são apagados, a menos que você acrescente `--volumes`.
 
Usa Docker? Os comandos são os mesmos, trocando `podman` por `docker`.
 
---

## Quando algo falha

### Lint

**`ruff format --check` falhou:** o código está fora do padrão de formatação. Corrija automaticamente com:

```bash
uv run ruff format .
```

**`ruff check` falhou:** a saída mostra o arquivo, a linha e a regra. Parte dos problemas tem correção automática:

```bash
uv run ruff check --fix .
```

### Testes

Rode só o teste que falhou para investigar mais rápido:

```bash
uv run pytest caminho/do/arquivo_test.py::nome_do_teste -v
```

### Build

Confira a mensagem de erro do Podman/Docker. As causas mais comuns são um pacote que falha ao instalar ou um `requirements.txt` desatualizado. Neste caso, rode `make lock` de novo.

Se aparecer `Erro: nenhum engine de container encontrado`, nem o Podman nem o Docker estão instalados (ou não estão no PATH).

### Scan (Trivy)

A saída lista cada problema com o identificador (ex.: `CVE-2025-12345`), o pacote e a severidade.

1. **Existe correção?** Se a coluna *Fixed Version* tiver uma versão, atualize o pacote (veja a seção 2) ou a imagem base.
2. **É falso positivo ou não se aplica ao projeto?** Registre no `.trivyignore`, conforme abaixo.

#### Ignorando um falso positivo

O Trivy lê automaticamente o arquivo `.trivyignore` na raiz do repositório. Cada linha contém um identificador a ignorar.

**Boas Práticas:**

- Toda entrada tem um comentário explicando **por que** foi ignorada.
- Toda entrada tem uma **data de expiração** (`exp:`). Quando a data passa, o Trivy volta a apontar o problema, e alguém precisa reavaliar.

```text
# Falso positivo: o Trivy detecta a versão errada do pacote X na imagem Wolfi.
# Avaliado por <nome> em 2026-11-02.
CVE-2025-12345 exp:2026-12-31
```

> Ignorar um alerta é uma decisão de segurança. Inclua a entrada no `.trivyignore` no mesmo PR da mudança, para que outra pessoa revise.

---

## Referência rápida

| Comando | Quando usar |
|---|---|
| `make help` | Ver todos os comandos |
| `make dev` | Desenvolver (API + frontend) |
| `make api` / `make ui` | Subir só uma parte |
| `make lock` | Depois de mexer no `requirements.in` |
| `make lint` | Checar estilo e erros |
| `make test` | Rodar os testes |
| `make build` | Construir a imagem |
| `make scan` | Escanear a imagem |
| `make ci-local` | **Antes de todo push** |