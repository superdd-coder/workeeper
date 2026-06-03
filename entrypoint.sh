#!/bin/bash
set -e

# Ensure data directories exist
mkdir -p data/qdrant data/history data/eval data/models data/hot_words data/meetings

# Start FastAPI (serves both API and frontend)
exec python -m src.main
