# MinerU API image pinned to the exact contract consumed by mineru_client.py.
# Based on the official MinerU 3.2.0 global Dockerfile, with the upstream
# unbounded `mineru[core]>=3.0.0` dependency replaced by an exact version.
FROM vllm/vllm-openai:v0.11.2

ARG MINERU_VERSION=3.2.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 \
    && fc-cache -fv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir \
        "mineru[core]==${MINERU_VERSION}" \
        --break-system-packages

# Build-time model download makes runtime startup deterministic and allows
# MINERU_MODEL_SOURCE=local. The named volume may still cache later updates.
RUN mineru-models-download -s huggingface -m all

LABEL org.opencontainers.image.title="xbrlbudget-mineru" \
      org.opencontainers.image.version="${MINERU_VERSION}" \
      org.opencontainers.image.source="https://github.com/opendatalab/MinerU"

ENTRYPOINT ["/bin/bash", "-c", "export MINERU_MODEL_SOURCE=local && exec \"$@\"", "--"]
