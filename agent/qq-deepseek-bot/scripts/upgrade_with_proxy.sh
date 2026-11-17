#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7890}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7890}"
export ALL_PROXY="${ALL_PROXY:-http://127.0.0.1:7890}"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost,::1"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/qq-uv-cache}"
export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" all_proxy="$ALL_PROXY" no_proxy="$NO_PROXY"
if ! curl --fail --silent --show-error --head --connect-timeout 5 --max-time 15 https://pypi.org/simple/pydantic-ai-slim/ >/dev/null; then
    echo '无法通过代理访问 PyPI；请检查本机 7890 监听和当前进程网络权限。' >&2
    exit 1
fi
uv sync --extra dev
uv run --no-sync pytest -q
