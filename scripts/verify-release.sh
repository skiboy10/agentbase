#!/bin/bash
#
# Release Verification Script
#
# Tests that a clean clone of the repository works without any local state.
# Run this before pushing releases to ensure the public repo is self-contained.
#
# Usage: ./scripts/verify-release.sh [--keep]
#   --keep    Keep the test directory for inspection (default: cleanup)
#
# Requirements:
# - Docker and docker compose
# - Git
# - curl

set -e

KEEP_DIR=false
if [ "$1" = "--keep" ]; then
    KEEP_DIR=true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TEST_DIR="/tmp/agentbase-release-test-$$"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() {
    if [ "$KEEP_DIR" = false ] && [ -d "$TEST_DIR" ]; then
        echo "Cleaning up test directory..."
        cd "$TEST_DIR" && docker compose down -v 2>/dev/null || true
        rm -rf "$TEST_DIR"
    fi
}

trap cleanup EXIT

echo "========================================"
echo "Agentbase Release Verification"
echo "========================================"
echo ""

# Step 1: Clone to temp directory
echo "[1/6] Cloning repository to temp directory..."
git clone --depth 1 "$REPO_ROOT" "$TEST_DIR"
cd "$TEST_DIR"

# Remove .git to ensure we're testing the files, not git state
rm -rf .git

# Step 2: Check for required files
echo "[2/6] Verifying required files..."
REQUIRED_FILES=(
    "docker-compose.yml"
    ".env.example"
    "backend/requirements.txt"
    "frontend/package.json"
    "docker/Dockerfile.backend"
    "docker/Dockerfile.frontend"
)

MISSING=0
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}  ✗ Missing: $file${NC}"
        MISSING=$((MISSING + 1))
    else
        echo "  ✓ Found: $file"
    fi
done

if [ $MISSING -gt 0 ]; then
    echo -e "${RED}FAILED: Missing required files${NC}"
    exit 1
fi

# Step 3: Setup environment
echo "[3/6] Setting up environment..."
cp .env.example .env

# Generate a test secret key
TEST_SECRET=$(openssl rand -hex 32)
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/^SECRET_KEY=.*/SECRET_KEY=$TEST_SECRET/" .env
else
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$TEST_SECRET/" .env
fi

# Use non-conflicting ports for testing
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' 's/^FRONTEND_PORT=.*/FRONTEND_PORT=3099/' .env
    sed -i '' 's/^BACKEND_PORT=.*/BACKEND_PORT=8099/' .env
    sed -i '' 's/^POSTGRES_PORT=.*/POSTGRES_PORT=5499/' .env
else
    sed -i 's/^FRONTEND_PORT=.*/FRONTEND_PORT=3099/' .env
    sed -i 's/^BACKEND_PORT=.*/BACKEND_PORT=8099/' .env
    sed -i 's/^POSTGRES_PORT=.*/POSTGRES_PORT=5499/' .env
fi

echo "  ✓ Environment configured with test ports (3099, 8099, 5499)"

# Step 4: Build containers
echo "[4/6] Building Docker containers..."
if ! docker compose build --quiet; then
    echo -e "${RED}FAILED: Docker build failed${NC}"
    exit 1
fi
echo "  ✓ Containers built successfully"

# Step 5: Start services
echo "[5/6] Starting services..."
docker compose up -d

# Wait for services to be healthy
echo "  Waiting for services to be healthy..."
MAX_WAIT=120
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    BACKEND_HEALTH=$(docker compose ps backend --format json 2>/dev/null | grep -o '"Health":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    POSTGRES_HEALTH=$(docker compose ps postgres --format json 2>/dev/null | grep -o '"Health":"[^"]*"' | cut -d'"' -f4 || echo "unknown")

    if [ "$BACKEND_HEALTH" = "healthy" ] && [ "$POSTGRES_HEALTH" = "healthy" ]; then
        break
    fi

    sleep 2
    WAITED=$((WAITED + 2))
    echo "  ... waiting ($WAITED/$MAX_WAIT seconds)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo -e "${YELLOW}WARNING: Services may not be fully healthy after ${MAX_WAIT}s${NC}"
    docker compose ps
fi

# Step 6: Smoke test
echo "[6/6] Running smoke tests..."
sleep 5  # Extra buffer for API to be ready

# Test backend health
if curl -sf http://localhost:8099/health > /dev/null 2>&1; then
    echo "  ✓ Backend health check passed"
else
    echo -e "${RED}  ✗ Backend health check failed${NC}"
    docker compose logs backend | tail -20
    exit 1
fi

# Test frontend
if curl -sf http://localhost:3099 > /dev/null 2>&1; then
    echo "  ✓ Frontend accessible"
else
    echo -e "${YELLOW}  ! Frontend not responding (may still be starting)${NC}"
fi

# Stop services
echo ""
echo "Stopping test services..."
docker compose down -v

echo ""
echo "========================================"
echo -e "${GREEN}Release verification PASSED${NC}"
echo "========================================"
echo ""
echo "The repository can be cloned and started without local state."

if [ "$KEEP_DIR" = true ]; then
    echo ""
    echo "Test directory preserved at: $TEST_DIR"
fi
