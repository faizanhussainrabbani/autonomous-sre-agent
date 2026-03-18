#!/usr/bin/env bash
# ===========================================================================
# SRE Agent — Unified Run Script
#
# Usage:
#   ./scripts/run.sh <command> [options]
#
# Commands:
#   setup          Install all Python dependencies (dev + intelligence)
#   server         Start the FastAPI API server
#   validate       Validate agent configuration
#   status         Print agent version and status
#   test           Run the full test suite
#   test:unit      Run unit tests only
#   test:e2e       Run E2E tests only
#   test:integ     Run integration tests (requires Docker/LocalStack)
#   lint           Run ruff linter + mypy type checker
#   format         Auto-format code with ruff
#   coverage       Run tests with coverage report
#   help           Show this help message
#
# Environment:
#   Loads .env file automatically if present in project root.
#   Set VENV_DIR to override the virtual environment path (default: .venv)
# ===========================================================================

set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
PYTHON="$VENV_DIR/bin/python"
PYTEST="$VENV_DIR/bin/pytest"
RUFF="$VENV_DIR/bin/ruff"
MYPY="$VENV_DIR/bin/mypy"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[⚠]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
header(){ echo -e "\n${CYAN}━━━ $1 ━━━${NC}\n"; }

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
    info "Loaded environment from .env"
fi

# ── Preflight checks ─────────────────────────────────────────────────────────
check_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        error "Virtual environment not found at $VENV_DIR. Run: python3 -m venv .venv"
    fi
    if [ ! -f "$PYTHON" ]; then
        error "Python not found in venv. Run: python3 -m venv .venv"
    fi
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_setup() {
    header "Setting Up Development Environment"

    if [ ! -d "$VENV_DIR" ]; then
        info "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi

    info "Installing all dependencies (dev + intelligence + aws + azure)..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -e ".[dev,intelligence,aws,azure]"

    info "Setup complete! Activate with: source .venv/bin/activate"
}

cmd_server() {
    check_venv
    header "Starting SRE Agent API Server"

    local host="${HOST:-0.0.0.0}"
    local port="${PORT:-8080}"
    local reload=""

    if [ "${1:-}" = "--reload" ]; then
        reload="--reload"
    fi

    info "Server starting on http://$host:$port"
    info "Docs: http://$host:$port/docs"
    "$VENV_DIR/bin/uvicorn" sre_agent.api.main:app \
        --host "$host" \
        --port "$port" \
        $reload
}

cmd_validate() {
    check_venv
    header "Validating Configuration"

    local config="${1:-$PROJECT_ROOT/config/agent.yaml}"
    "$PYTHON" -m sre_agent.api.cli validate -c "$config"
}

cmd_status() {
    check_venv
    header "Agent Status"
    "$PYTHON" -m sre_agent.api.cli status
}

cmd_test() {
    check_venv
    header "Running Full Test Suite"
    "$PYTEST" tests/ -v --tb=short "$@"
}

cmd_test_unit() {
    check_venv
    header "Running Unit Tests"
    "$PYTEST" tests/unit/ -v --tb=short "$@"
}

cmd_test_e2e() {
    check_venv
    header "Running E2E Tests"
    "$PYTEST" tests/e2e/ -v --tb=short "$@"
}

cmd_test_integ() {
    check_venv
    header "Running Integration Tests"
    warn "Integration tests require Docker and/or LocalStack Pro."
    "$PYTEST" tests/integration/ -v --tb=short "$@"
}

cmd_lint() {
    check_venv
    header "Running Linters"

    info "Running ruff..."
    "$RUFF" check src/ tests/

    info "Running mypy..."
    "$MYPY" src/sre_agent/

    info "All lint checks passed."
}

cmd_format() {
    check_venv
    header "Formatting Code"
    "$RUFF" format src/ tests/
    "$RUFF" check src/ tests/ --fix
    info "Formatting complete."
}

cmd_coverage() {
    check_venv
    header "Running Tests with Coverage"
    "$PYTEST" tests/ --cov=src/sre_agent --cov-report=term-missing --cov-report=html "$@"
    info "HTML coverage report: htmlcov/index.html"
}

cmd_help() {
    cat <<'EOF'
🤖 Autonomous SRE Agent — Run Script

Usage:  ./scripts/run.sh <command> [options]

Commands:
  setup              Install dependencies (creates venv if needed)
  server [--reload]  Start FastAPI server (--reload for dev mode)
  validate [config]  Validate YAML config (default: config/agent.yaml)
  status             Print agent version and status
  test               Run full test suite (501 tests)
  test:unit          Run unit tests only (~400 tests, fast)
  test:e2e           Run E2E tests only
  test:integ         Run integration tests (Docker required)
  lint               Run ruff + mypy
  format             Auto-format code with ruff
  coverage           Run tests with coverage report
  help               Show this message

Environment Variables:
  HOST       API server host (default: 0.0.0.0)
  PORT       API server port (default: 8080)
  VENV_DIR   Path to virtual environment (default: .venv)

A .env file in the project root is auto-loaded if present.
Copy .env.example to .env and fill in your secrets.
EOF
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
COMMAND="${1:-help}"
shift 2>/dev/null || true

case "$COMMAND" in
    setup)      cmd_setup "$@" ;;
    server)     cmd_server "$@" ;;
    validate)   cmd_validate "$@" ;;
    status)     cmd_status "$@" ;;
    test)       cmd_test "$@" ;;
    test:unit)  cmd_test_unit "$@" ;;
    test:e2e)   cmd_test_e2e "$@" ;;
    test:integ) cmd_test_integ "$@" ;;
    lint)       cmd_lint "$@" ;;
    format)     cmd_format "$@" ;;
    coverage)   cmd_coverage "$@" ;;
    help|--help|-h)  cmd_help ;;
    *)
        error "Unknown command: $COMMAND. Run './scripts/run.sh help' for usage."
        ;;
esac
