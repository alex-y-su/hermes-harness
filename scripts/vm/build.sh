#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
docker build \
  -f docker/local-vm/Dockerfile \
  --target base \
  -t hermes-harness-local-vm:latest \
  .
