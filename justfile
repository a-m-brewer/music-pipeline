python := ".venv/bin/python"

default: run

setup:
    #!/usr/bin/env bash
    set -euo pipefail
    python3 -m venv .venv
    .venv/bin/pip install -e .
    if [[ "$(uname)" == "Darwin" ]]; then
        brew install chromaprint
    elif command -v apt-get &>/dev/null; then
        sudo apt-get install -y libchromaprint-tools
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y chromaprint-tools
    else
        echo "Warning: could not install chromaprint automatically. Install it manually for audio fingerprinting."
    fi
    echo ""
    echo "Setup complete."
    echo "Then copy config: cp config.example.yaml config.yaml"

run:
    {{python}} -m music_pipeline.main

scan:
    {{python}} -m music_pipeline.main --scan-only

review:
    {{python}} -m music_pipeline.main --review

stats:
    {{python}} -m music_pipeline.main --stats

batch-approve MIN="85":
    {{python}} -m music_pipeline.main --batch-approve {{MIN}}
