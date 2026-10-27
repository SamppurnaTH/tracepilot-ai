# Sandbox image for running the application under investigation.
# Containers from this image run with no network, a read-only root filesystem,
# no capabilities and a non-root user (see backend/app/sandbox.py).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

RUN useradd --create-home --uid 10001 sandbox
USER sandbox
WORKDIR /workspace
