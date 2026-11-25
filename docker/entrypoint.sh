#!/bin/sh
# Bootstraps data on first start (shared volume /app/data), then runs the requested service.
set -e
if [ ! -f data/shop.db ]; then
  echo "[bootstrap] generating catalog + loading SQLite"
  python scripts/generate_data.py && python scripts/load_db.py
fi
case "$1" in
  api)
    if [ ! -d data/qdrant ]; then
      echo "[bootstrap] building vector index (needs OPENAI_API_KEY)"
      python -m laptop_agent.rag.index
    fi
    exec uvicorn laptop_agent.api.main:app --host 0.0.0.0 --port 8000 ;;
  mcp)  exec python -m laptop_agent.mcp_cart.server --http --port 8765 ;;
  ui)   exec streamlit run ui/app.py --server.address 0.0.0.0 --server.port 8501 ;;
  *)    exec "$@" ;;
esac
