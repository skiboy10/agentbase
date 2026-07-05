#!/bin/bash
# ============================================================================
# Agentbase Test Runner
# ============================================================================
# Unified script for running all tests across backend and frontend.
#
# Usage:
#   ./scripts/test.sh           # Run all tests
#   ./scripts/test.sh backend   # Run backend tests only
#   ./scripts/test.sh frontend  # Run frontend tests only
#   ./scripts/test.sh --watch   # Run tests in watch mode
#   ./scripts/test.sh --coverage # Run with coverage reports
#
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Default options
RUN_BACKEND=true
RUN_FRONTEND=true
WATCH_MODE=false
COVERAGE=false
VERBOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        backend)
            RUN_FRONTEND=false
            shift
            ;;
        frontend)
            RUN_BACKEND=false
            shift
            ;;
        --watch|-w)
            WATCH_MODE=true
            shift
            ;;
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Agentbase Test Runner"
            echo ""
            echo "Usage: ./scripts/test.sh [options] [target]"
            echo ""
            echo "Targets:"
            echo "  backend    Run backend tests only"
            echo "  frontend   Run frontend tests only"
            echo "  (none)     Run all tests"
            echo ""
            echo "Options:"
            echo "  --watch, -w     Run tests in watch mode"
            echo "  --coverage, -c  Generate coverage reports"
            echo "  --verbose, -v   Verbose output"
            echo "  --help, -h      Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Print header
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}       Agentbase Test Runner${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Track overall status
BACKEND_STATUS=0
FRONTEND_STATUS=0

# Run backend tests
run_backend_tests() {
    echo -e "${YELLOW}Running Backend Tests...${NC}"
    echo ""

    cd "$BACKEND_DIR"

    # Set test environment
    export TESTING=true
    export DATABASE_URL="sqlite+aiosqlite:///./test.db"

    # Build pytest command
    PYTEST_ARGS=("tests/" "-v")

    if [ "$COVERAGE" = true ]; then
        PYTEST_ARGS+=("--cov=app" "--cov-report=term-missing" "--cov-report=html:coverage_html")
    fi

    if [ "$VERBOSE" = true ]; then
        PYTEST_ARGS+=("-vv")
    fi

    # Run tests
    if python -m pytest "${PYTEST_ARGS[@]}"; then
        echo ""
        echo -e "${GREEN}Backend tests passed!${NC}"
        BACKEND_STATUS=0
    else
        echo ""
        echo -e "${RED}Backend tests failed!${NC}"
        BACKEND_STATUS=1
    fi

    # Clean up test database
    rm -f test.db

    cd "$PROJECT_ROOT"
}

# Run frontend tests
run_frontend_tests() {
    echo -e "${YELLOW}Running Frontend Tests...${NC}"
    echo ""

    cd "$FRONTEND_DIR"

    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}Installing dependencies...${NC}"
        npm install
    fi

    # Build vitest command
    if [ "$WATCH_MODE" = true ]; then
        npm run test
        FRONTEND_STATUS=$?
    elif [ "$COVERAGE" = true ]; then
        if npm run test:coverage; then
            echo ""
            echo -e "${GREEN}Frontend tests passed!${NC}"
            FRONTEND_STATUS=0
        else
            echo ""
            echo -e "${RED}Frontend tests failed!${NC}"
            FRONTEND_STATUS=1
        fi
    else
        if npm run test:run; then
            echo ""
            echo -e "${GREEN}Frontend tests passed!${NC}"
            FRONTEND_STATUS=0
        else
            echo ""
            echo -e "${RED}Frontend tests failed!${NC}"
            FRONTEND_STATUS=1
        fi
    fi

    cd "$PROJECT_ROOT"
}

# Run tests
if [ "$RUN_BACKEND" = true ]; then
    run_backend_tests
    echo ""
fi

if [ "$RUN_FRONTEND" = true ]; then
    run_frontend_tests
    echo ""
fi

# Print summary
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}                 Summary${NC}"
echo -e "${BLUE}============================================${NC}"

if [ "$RUN_BACKEND" = true ]; then
    if [ $BACKEND_STATUS -eq 0 ]; then
        echo -e "Backend:  ${GREEN}PASSED${NC}"
    else
        echo -e "Backend:  ${RED}FAILED${NC}"
    fi
fi

if [ "$RUN_FRONTEND" = true ]; then
    if [ $FRONTEND_STATUS -eq 0 ]; then
        echo -e "Frontend: ${GREEN}PASSED${NC}"
    else
        echo -e "Frontend: ${RED}FAILED${NC}"
    fi
fi

echo ""

# Exit with appropriate status
if [ $BACKEND_STATUS -ne 0 ] || [ $FRONTEND_STATUS -ne 0 ]; then
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
