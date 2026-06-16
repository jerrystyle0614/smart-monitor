#!/bin/bash
cd "$(dirname "$0")"
source .env
export PYTHONUNBUFFERED=1
mkdir -p log
exec /Library/Frameworks/Python.framework/Versions/3.9/bin/uvicorn bot.server:app --port 8000 >> log/server.log 2>&1
