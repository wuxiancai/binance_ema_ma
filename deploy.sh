#!/usr/bin/env bash
set -euo pipefail

PY=${PY:-python3}

echo "[deploy] installing requirements..."
${PY} -m pip install -r requirements.txt

echo "[deploy] starting web server..."
${PY} web_main.py