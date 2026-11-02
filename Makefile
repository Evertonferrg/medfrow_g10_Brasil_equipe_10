# ==============================================================================
#  Como usar o Makefile
# ==============================================================================
#
#  Uso rápido:
#    make dev        →  Inicia tanto Backend quantro Frontend
#    make ci-local   →  Roda toda as verificações antes de todo git push
#    make help       →  lista todos os comandos disponíveis
#
#  Guia completo: ./docs/03-makefile/03-makefile.md
#
#  Engine de container: usa Podman se instalado; caso contrário, Docker.
#
# ==============================================================================

# ------------------------------------------------------------------------------
#  Configuração
# ------------------------------------------------------------------------------
ENGINE         ?= $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)
IMAGE_NAME     := mediflow-agent
IMAGE_TAG      := dev
PYTHON_VERSION := 3.13

.DEFAULT_GOAL := help
.PHONY: help lock api ui dev lint test build scan ci-local

# ------------------------------------------------------------------------------
#  Ajuda
# ------------------------------------------------------------------------------
help: ## Mostra esta lista de comandos
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------------------
#  1. Dependências
# ------------------------------------------------------------------------------
lock: ## Gera requirements.txt com hashes para o Linux do container
	uv pip compile requirements.in \
		--generate-hashes \
		--python-version $(PYTHON_VERSION) \
		--python-platform x86_64-unknown-linux-gnu \
		-o requirements.txt

# ------------------------------------------------------------------------------
#  2. Execução de código
# ------------------------------------------------------------------------------
api: ## Inicia a API FastAPI (porta 8000)
	uv run uvicorn app.api.main:app --reload --port 8000

ui: ## Inicia o frontend Streamlit (porta 8501)
	uv run streamlit run ui/Home.py

dev: ## Inicia tanto a API quanto o Streamlit simultaneamente
	@trap 'kill 0' EXIT; uv run uvicorn app.api.main:app --reload --port 8000 & uv run streamlit run ui/Home.py

# ------------------------------------------------------------------------------
#  3. Qualidade de código
# ------------------------------------------------------------------------------
lint: ## Lint e checagem de formatação (ruff)
	uv run ruff check .
	uv run ruff format --check .

test: ## Testes unitários (contratos JSON e nós do LangGraph)
	uv run pytest -v

# ------------------------------------------------------------------------------
#  4. Container
# ------------------------------------------------------------------------------
build: ## Build da imagem com Podman/Docker
	@test -n "$(ENGINE)" || { echo "Erro: nenhum engine de container encontrado. Instale Podman ou Docker."; exit 1; }
	$(ENGINE) build \
		--build-arg PYTHON_VERSION=$(PYTHON_VERSION) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) .

scan: ## Trivy (config + vulnerabilidades + segredos); lê o .trivyignore
	trivy config --exit-code 1 --severity MEDIUM,HIGH,CRITICAL .
	trivy image --exit-code 1 --scanners vuln,secret \
		--severity LOW,MEDIUM,HIGH,CRITICAL $(IMAGE_NAME):$(IMAGE_TAG)

# ------------------------------------------------------------------------------
#  5. Pipeline local
# ------------------------------------------------------------------------------
ci-local: lint test build scan ## Roda todas as verificações antes do push