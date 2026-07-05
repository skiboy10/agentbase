#!/bin/bash
# Run tests inside Docker container
# Usage: ./run_tests.sh [pytest args]

set -e

echo "Installing test dependencies..."
pip install aiosqlite httpx pytest-asyncio --quiet

echo "Running tests..."
cd /app
python -m pytest tests/ -v "$@"
