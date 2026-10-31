# ==========================================
# Estágio 1: Builder
# ==========================================
# trivy:ignore:DS-0001
FROM cgr.dev/chainguard/wolfi-base:latest AS builder

WORKDIR /app

# Defina aqui a mesma versão do Python usada para gerar os hashes (ex: 3.13 ou 3.14)
ARG PYTHON_VERSION=3.13

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk update && \
    apk add --no-cache python-${PYTHON_VERSION} py${PYTHON_VERSION}-pip

RUN python${PYTHON_VERSION} -m venv $VIRTUAL_ENV

COPY requirements.txt .
# Instala exigindo a verificação de hashes e sem depender de compiladores externos (only-binary)
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt && \
    pip uninstall -y pip setuptools wheel

# ==========================================
# Estágio 2: Runtime
# ==========================================
# trivy:ignore:DS-0001
FROM cgr.dev/chainguard/wolfi-base:latest

WORKDIR /app

ARG PYTHON_VERSION=3.13

RUN apk update && \
    apk add --no-cache python-${PYTHON_VERSION} && \
    chown -R nonroot:nonroot /app && \
    rm -rf /var/cache/apk/*

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder --chown=nonroot:nonroot /app/.venv /app/.venv
COPY --chown=nonroot:nonroot . /app/

USER nonroot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]

ENTRYPOINT ["python3", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]