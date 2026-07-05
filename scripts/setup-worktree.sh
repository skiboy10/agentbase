#!/bin/bash
#
# setup-worktree.sh - Create a git worktree for parallel development
#
# Creates a new worktree in ../agentbase-trees/{branch-name} with:
# - A symlink to the main extensions/ directory
# - A copy of .env (if it exists)
#
# Usage:
#   ./scripts/setup-worktree.sh <branch-name>
#
# Example:
#   ./scripts/setup-worktree.sh feature/new-agent
#
# This allows you to work on multiple branches simultaneously, each with
# their own checkout but sharing the same extensions.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for branch name argument
if [ -z "$1" ]; then
    echo -e "${RED}Error: Branch name required${NC}"
    echo ""
    echo "Usage: $0 <branch-name>"
    echo ""
    echo "Examples:"
    echo "  $0 feature/new-agent"
    echo "  $0 fix/bug-123"
    exit 1
fi

BRANCH_NAME="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TREES_DIR="$(cd "$REPO_ROOT/.." && pwd)/agentbase-trees"
WORKTREE_DIR="$TREES_DIR/$BRANCH_NAME"

echo -e "${GREEN}Setting up worktree for branch: ${BRANCH_NAME}${NC}"
echo ""

# Create trees directory if it doesn't exist
if [ ! -d "$TREES_DIR" ]; then
    echo "Creating worktrees directory: $TREES_DIR"
    mkdir -p "$TREES_DIR"
fi

# Check if worktree already exists
if [ -d "$WORKTREE_DIR" ]; then
    echo -e "${YELLOW}Warning: Worktree already exists at $WORKTREE_DIR${NC}"
    echo "To remove it, run: git worktree remove $WORKTREE_DIR"
    exit 1
fi

# Check if branch exists (local or remote)
if git rev-parse --verify "$BRANCH_NAME" >/dev/null 2>&1; then
    echo "Using existing branch: $BRANCH_NAME"
    git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"
elif git rev-parse --verify "origin/$BRANCH_NAME" >/dev/null 2>&1; then
    echo "Checking out remote branch: origin/$BRANCH_NAME"
    git worktree add "$WORKTREE_DIR" -b "$BRANCH_NAME" "origin/$BRANCH_NAME"
else
    echo "Creating new branch: $BRANCH_NAME"
    git worktree add "$WORKTREE_DIR" -b "$BRANCH_NAME"
fi

echo ""

# Create symlink to extensions directory
echo "Creating symlink to extensions..."
if [ -d "$REPO_ROOT/extensions" ]; then
    # Remove empty extensions dir if it exists in worktree
    rmdir "$WORKTREE_DIR/extensions" 2>/dev/null || true
    ln -sf "$REPO_ROOT/extensions" "$WORKTREE_DIR/extensions"
    echo -e "  ${GREEN}✓${NC} Linked extensions/ -> $REPO_ROOT/extensions"
else
    echo -e "  ${YELLOW}⚠${NC} No extensions/ directory found in main repo"
fi

# Copy .env if it exists
echo "Copying environment files..."
if [ -f "$REPO_ROOT/.env" ]; then
    cp "$REPO_ROOT/.env" "$WORKTREE_DIR/.env"
    echo -e "  ${GREEN}✓${NC} Copied .env"
else
    echo -e "  ${YELLOW}⚠${NC} No .env file found (copy .env.example manually)"
fi

# Copy .env.local if it exists
if [ -f "$REPO_ROOT/.env.local" ]; then
    cp "$REPO_ROOT/.env.local" "$WORKTREE_DIR/.env.local"
    echo -e "  ${GREEN}✓${NC} Copied .env.local"
fi

echo ""
echo -e "${GREEN}Worktree created successfully!${NC}"
echo ""
echo "Location: $WORKTREE_DIR"
echo ""
echo "To start working:"
echo -e "  ${YELLOW}cd $WORKTREE_DIR${NC}"
echo ""
echo "To start Claude Code in the worktree:"
echo -e "  ${YELLOW}cd $WORKTREE_DIR && claude${NC}"
echo ""
echo "To start Docker services:"
echo -e "  ${YELLOW}cd $WORKTREE_DIR && docker compose up -d${NC}"
echo ""
echo "To remove this worktree later:"
echo -e "  ${YELLOW}git worktree remove $WORKTREE_DIR${NC}"
