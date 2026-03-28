python := ".venv/bin/python"

default: run

setup:
    python3 -m venv .venv
    .venv/bin/pip install -e .
    brew install chromaprint
    @echo ""
    @echo "Setup complete."
    @echo "Then copy config: cp config.example.yaml config.yaml"

run:
    {{python}} -m music_pipeline.main

scan:
    {{python}} -m music_pipeline.main --scan-only

review:
    {{python}} -m music_pipeline.main --review

stats:
    {{python}} -m music_pipeline.main --stats
