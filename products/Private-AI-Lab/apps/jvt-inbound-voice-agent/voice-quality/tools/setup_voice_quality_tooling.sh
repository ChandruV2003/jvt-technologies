#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv-voice-quality"

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install imageio-ffmpeg

cat > "$ROOT/tooling-status.txt" <<EOF
generated_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
venv=$VENV
python=$("$VENV/bin/python" --version 2>&1)
imageio_ffmpeg=installed
purpose=Decode browser WebM voice samples into normalized local WAV assets for internal quality evaluation.
EOF
