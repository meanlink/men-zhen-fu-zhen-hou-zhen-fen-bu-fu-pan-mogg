#!/usr/bin/env bash
set -e
python -c "from src.database import init_db; init_db()"
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
