#!/bin/sh
set -e

# Build FAISS index at first boot (Railway injects env vars at runtime, not build time)
if [ ! -d "/app/faiss_index" ] || [ -z "$(ls -A /app/faiss_index 2>/dev/null)" ]; then
    echo "[startup] faiss_index not found — building now..."
    python app/rag_indexer.py
    echo "[startup] faiss_index built successfully"
else
    echo "[startup] faiss_index already exists — skipping rebuild"
fi

exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}"
