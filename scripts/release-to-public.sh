#!/bin/bash
#
# Release to Public Repository
#
# Pushes a clean release to the public agentbase repo, excluding:
# - Extensions (except _template)
# - Data files
# - Local overrides
# - Development artifacts
#
# Usage: ./scripts/release-to-public.sh [version-tag]
#   version-tag    Optional tag (e.g., v1.0.0). If omitted, pushes without tagging.
#
# Example:
#   ./scripts/release-to-public.sh           # Push latest changes
#   ./scripts/release-to-public.sh v1.0.0    # Push and tag as v1.0.0

set -e

PUBLIC_REPO="https://github.com/skiboy10/agentbase-public.git"
VERSION_TAG="$1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RELEASE_DIR="/tmp/agentbase-release-$$"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() {
    if [ -d "$RELEASE_DIR" ]; then
        rm -rf "$RELEASE_DIR"
    fi
}

trap cleanup EXIT

echo "========================================"
echo "Agentbase Public Release"
echo "========================================"
echo ""

# Step 1: Verify we're in a clean state
echo "[1/6] Checking repository state..."
cd "$REPO_ROOT"

if ! git diff --quiet; then
    echo -e "${YELLOW}WARNING: You have uncommitted changes${NC}"
    echo "Consider committing or stashing before release."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

CURRENT_COMMIT=$(git rev-parse --short HEAD)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "  Source: $CURRENT_BRANCH @ $CURRENT_COMMIT"

# Step 2: Clone public repo
echo "[2/6] Cloning public repository..."
git clone --depth 1 "$PUBLIC_REPO" "$RELEASE_DIR" 2>/dev/null || {
    echo "  Public repo is empty, initializing..."
    mkdir -p "$RELEASE_DIR"
    cd "$RELEASE_DIR"
    git init
    git remote add origin "$PUBLIC_REPO"
    cd "$REPO_ROOT"
}

# Step 3: Sync files (excluding private content)
echo "[3/6] Syncing files to release directory..."

# Use rsync to copy, excluding private content
rsync -av --delete \
    --exclude='.git' \
    --exclude='.git/' \
    --exclude='extensions/*' \
    --exclude='data/' \
    --exclude='docker-compose.override.yml' \
    --exclude='.env' \
    --exclude='.env.local' \
    --exclude='*.db' \
    --exclude='*.sqlite' \
    --exclude='*.sqlite3' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='node_modules/' \
    --exclude='frontend/dist/' \
    --exclude='.pytest_cache/' \
    --exclude='.venv/' \
    --exclude='venv/' \
    --exclude='.DS_Store' \
    --exclude='*.log' \
    --exclude='.claude/' \
    --exclude='.agent/' \
    --exclude='.playwright-mcp/' \
    --exclude='test-files/' \
    --exclude='knowledge/' \
    --exclude='knowledge-base/' \
    --exclude='docs/TEST_RESULTS_*.md' \
    --exclude='docs/TEST_PLAN_*.md' \
    --exclude='docs/EXTENSION_DECOUPLING_*.md' \
    --exclude='docs/v1-public-release-plan.md' \
    --exclude='docs/plans/' \
    --exclude='docs/INGESTION_IMPROVEMENTS.md' \
    --exclude='BACKLOG_*.md' \
    --exclude='scripts/agent_scripts/' \
    --include='frontend/public/agentbase-logo.png' \
    --exclude='*.png' \
    --exclude='*.jpg' \
    --exclude='*.jpeg' \
    "$REPO_ROOT/" "$RELEASE_DIR/"

# Remove any excluded directories that might exist from previous syncs
rm -rf "$RELEASE_DIR/knowledge-base" "$RELEASE_DIR/knowledge" "$RELEASE_DIR/.playwright-mcp" "$RELEASE_DIR/.agent" "$RELEASE_DIR/test-files"

echo "  Files synced successfully"

# Step 4: Check for sensitive content
echo "[4/6] Scanning for sensitive content..."
cd "$RELEASE_DIR"

SENSITIVE_FOUND=0

# Check for API keys or secrets in code files (exclude docs - they have example patterns)
# Require longer matches to avoid false positives on placeholders like "sk-ant-..."
SUSPICIOUS_FILES=$(grep -r -l -E "sk-[a-zA-Z0-9]{40,}" --include="*.py" --include="*.ts" --include="*.js" --include="*.json" . 2>/dev/null || true)
if [ -n "$SUSPICIOUS_FILES" ]; then
    echo -e "${RED}ERROR: Potential API keys found in code files!${NC}"
    echo "$SUSPICIOUS_FILES"
    SENSITIVE_FOUND=1
fi

# Check for .env files that shouldn't be there
if find . -name ".env" -o -name ".env.local" 2>/dev/null | grep -q .; then
    echo -e "${RED}ERROR: .env files found in release!${NC}"
    SENSITIVE_FOUND=1
fi

# Check for database files
if find . -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" 2>/dev/null | grep -q .; then
    echo -e "${RED}ERROR: Database files found in release!${NC}"
    SENSITIVE_FOUND=1
fi

if [ $SENSITIVE_FOUND -eq 1 ]; then
    echo -e "${RED}Release aborted due to sensitive content.${NC}"
    exit 1
fi

echo "  No sensitive content detected"

# Step 5: Commit changes
echo "[5/6] Committing changes..."

git add -A

if git diff --cached --quiet; then
    echo "  No changes to commit"
else
    COMMIT_MSG="Release from $CURRENT_BRANCH @ $CURRENT_COMMIT"
    if [ -n "$VERSION_TAG" ]; then
        COMMIT_MSG="Release $VERSION_TAG from $CURRENT_BRANCH @ $CURRENT_COMMIT"
    fi

    git commit -m "$COMMIT_MSG

Source commit: $CURRENT_COMMIT
Source branch: $CURRENT_BRANCH
Released: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"

    echo "  Committed: $COMMIT_MSG"
fi

# Step 6: Push and optionally tag
echo "[6/6] Pushing to public repository..."

# Push (handle empty repo case)
if git rev-parse --verify origin/main >/dev/null 2>&1; then
    git push origin main
else
    git push -u origin main 2>/dev/null || git push -u origin HEAD:main
fi

if [ -n "$VERSION_TAG" ]; then
    git tag -a "$VERSION_TAG" -m "Release $VERSION_TAG"
    git push origin "$VERSION_TAG"
    echo "  Tagged as: $VERSION_TAG"
fi

echo ""
echo "========================================"
echo -e "${GREEN}Release pushed successfully!${NC}"
echo "========================================"
echo ""
echo "Public repo: https://github.com/skiboy10/agentbase-public"
if [ -n "$VERSION_TAG" ]; then
    echo "Release tag: $VERSION_TAG"
fi
echo ""
echo "Next steps:"
echo "  1. Verify the release: https://github.com/skiboy10/agentbase-public"
echo "  2. Run verification:   ./scripts/verify-release.sh"
