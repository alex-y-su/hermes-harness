FROM python:3.11-slim AS base

ENV DEBIAN_FRONTEND=noninteractive \
    HERMES_HOME=/vm/hermes-home \
    HERMES_INSTALL_DIR=/usr/local/lib/hermes-agent \
    FACTORY_DIR=/vm/factory \
    PATH=/usr/local/bin:/root/.local/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      git \
      jq \
      ripgrep \
      sqlite3 \
      xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/vm/install-hermes.sh /usr/local/bin/install-hermes-agent
COPY scripts/hermes/install-mock-kanban.sh /usr/local/bin/install-mock-kanban
COPY scripts/hermes/mock_remote_kanban.py /usr/local/share/hermes-harness/mock_remote_kanban.py
RUN chmod +x /usr/local/bin/install-hermes-agent \
    && chmod +x /usr/local/bin/install-mock-kanban \
    && install-hermes-agent \
    && HERMES_MOCK_KANBAN_SRC=/usr/local/share/hermes-harness/mock_remote_kanban.py install-mock-kanban

WORKDIR /workspace

CMD ["bash"]

FROM base AS dashboard

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) node_arch="x64" ;; \
      arm64) node_arch="arm64" ;; \
      *) echo "unsupported architecture for Node install: $arch" >&2; exit 1 ;; \
    esac; \
    node_version="v22.22.2"; \
    curl -fsSL "https://nodejs.org/dist/${node_version}/node-${node_version}-linux-${node_arch}.tar.xz" -o /tmp/node.tar.xz; \
    mkdir -p /root/.hermes/node; \
    tar -xJf /tmp/node.tar.xz -C /root/.hermes/node --strip-components=1; \
    ln -sfn /root/.hermes/node/bin/node /usr/local/bin/node; \
    ln -sfn /root/.hermes/node/bin/npm /usr/local/bin/npm; \
    ln -sfn /root/.hermes/node/bin/npx /usr/local/bin/npx; \
      HERMES_INSTALL_BROWSER_TOOLS=1 install-hermes-agent \
    && HERMES_MOCK_KANBAN_SRC=/usr/local/share/hermes-harness/mock_remote_kanban.py install-mock-kanban \
    && cd "$HERMES_INSTALL_DIR/web" \
    && npm install \
    && npm run build \
    && rm -rf /root/.cache/uv /root/.cache/pip /root/.npm/_cacache /tmp/node.tar.xz
