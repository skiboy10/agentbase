#!/bin/bash
#
# Setup script for agentbase git hooks
#
# This configures git to use the hooks in .githooks/ directory
# Run this once after cloning or to re-enable hooks.
#
# Usage: ./scripts/setup-git-hooks.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Setting up git hooks for agentbase..."

# Configure git to use .githooks directory
git config core.hooksPath .githooks

# Verify hooks are executable
if [ -f "$REPO_ROOT/.githooks/pre-commit" ]; then
    chmod +x "$REPO_ROOT/.githooks/pre-commit"
    echo "✓ Pre-commit hook configured"
else
    echo "✗ Pre-commit hook not found at .githooks/pre-commit"
    exit 1
fi

echo ""
echo "Git hooks setup complete!"
echo "Hooks directory: .githooks/"
echo ""
echo "To disable hooks temporarily: git commit --no-verify"
echo "To disable hooks permanently: git config --unset core.hooksPath"
