FROM e2bdev/base

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        jq \
        nodejs \
        npm \
        python3 \
        python3-pip \
        ripgrep \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex@0.128.0
RUN python3 -m pip install --break-system-packages hermes-harness || true
