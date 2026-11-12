#!/usr/bin/env bash
set -euo pipefail

XV6_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "$XV6_DIR/.." && pwd -P)"
ENV_FILE="$PROJECT_ROOT/.env"
VENV_DIR="$PROJECT_ROOT/.venv"

if [[ ! -f "$ENV_FILE" && -z "${NVIDIA_API_KEY:-}" ]]; then
    printf 'Missing configuration file: %s\n' "$ENV_FILE" >&2
    printf 'Create it with NVIDIA_API_KEY=YOUR_KEY_HERE and replace the placeholder, or export NVIDIA_API_KEY.\n' >&2
    exit 1
fi

if [[ ! -f "$VENV_DIR/bin/activate" || ! -x "$VENV_DIR/bin/python" ]]; then
    printf 'Project virtual environment not found at %s\n' "$VENV_DIR" >&2
    printf 'Create it and install %s/requirements.txt; this launcher will not create one.\n' "$XV6_DIR" >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if ! python -c 'import openai, dotenv' >/dev/null 2>&1; then
    printf 'Required Python dependencies are missing.\n' >&2
    printf 'Install them with: %s/bin/python -m pip install -r %s/requirements.txt\n' \
        "$VENV_DIR" "$XV6_DIR" >&2
    exit 1
fi

if ! python - "$ENV_FILE" <<'PY'
import os
import sys
from dotenv import load_dotenv

load_dotenv(dotenv_path=sys.argv[1], override=False)
key = os.environ.get("NVIDIA_API_KEY")
sys.exit(0 if key and key != "YOUR_KEY_HERE" else 1)
PY
then
    printf 'NVIDIA_API_KEY is missing or still the placeholder.\n' >&2
    printf 'Set it in the environment or replace the value in %s.\n' "$ENV_FILE" >&2
    exit 1
fi

cd "$XV6_DIR"
exec "$VENV_DIR/bin/python" run_agent.py
