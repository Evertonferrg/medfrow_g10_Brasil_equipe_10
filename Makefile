# ==============================================================================
#  Como usar o Makefile
# ==============================================================================
#
#  Uso rápido:
#    make lock       →  depois de adicionar/alterar pacotes em requirements.in
#    make ci-local   →  antes de todo git push
#    make help       →  lista todos os comandos disponíveis
#
#  Engine de container: usa Podman se instalado; caso contrário, Docker.
#
# ==============================================================================

ENGINE ?= $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)
IMAGE_NAME := mediflow-agent
IMAGE_TAG := dev
PYTHON_VERSION := 3.13

.PHONY: lock lint test build scan ci-local

## 1. Gera requirements.txt hasheado especificamente para o Linux do Container
lock:
	uv pip compile requirements.in \
		--generate-hashes \
		--python-version $(PYTHON_VERSION) \
		--python-platform x86_64-unknown-linux-gnu \
		-o requirements.txt

## 2. Lint e checagem de formatação (ruff)
lint:
	uv run ruff check .
	uv run ruff format --check .

## 3. Testes unitários (contratos JSON e nós do LangGraph)
test:
	uv run pytest -v

## 4. Build da imagem com Podman/Docker
build:
	$(ENGINE) build \
		--build-arg PYTHON_VERSION=$(PYTHON_VERSION) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) .

## 5. Auditoria completa com Trivy (Config + Imagem + Segredos)
scan:
	trivy config --exit-code 1 --severity MEDIUM,HIGH,CRITICAL .
	trivy image --exit-code 1 --scanners vuln,secret --severity LOW,MEDIUM,HIGH,CRITICAL $(IMAGE_NAME):$(IMAGE_TAG)

## Pipeline completo na máquina do Dev
ci-local: lint test build scan