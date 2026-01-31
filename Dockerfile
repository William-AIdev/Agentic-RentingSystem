# syntax=docker/dockerfile:1.6

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---------- deps: prod ----------
FROM base AS deps-prod
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# ---------- deps: dev ----------
FROM base AS deps-dev
COPY requirements.txt requirements-dev.txt requirements-test.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements-dev.txt

# ---------- runtime: prod ----------
FROM python:3.12-slim AS prod

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /app

COPY --from=deps-prod /usr/local /usr/local
COPY . /app

EXPOSE 7860
CMD ["python", "-m", "app.main"]

# ---------- runtime: dev ----------
FROM python:3.12-slim AS dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /app

COPY --from=deps-dev /usr/local /usr/local
COPY . /app

EXPOSE 7860
CMD ["python", "-m", "app.main"]
