#!/usr/bin/env bash
# ===========================================================================
# SRE Agent — External Dependencies Manager
#
# Manages Docker containers for local development dependencies:
#   - LocalStack Pro (AWS API emulation)
#   - Prometheus (metrics)
#   - Jaeger (traces)
#
# Usage:
#   ./scripts/setup_deps.sh start       Start all services
#   ./scripts/setup_deps.sh stop        Stop all services
#   ./scripts/setup_deps.sh status      Show service status
#   ./scripts/setup_deps.sh logs        Tail service logs
#   ./scripts/setup_deps.sh clean       Stop + remove volumes
#   ./scripts/setup_deps.sh health      Check health of all services
#
# Prerequisites: Docker, Docker Compose v2+
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.deps.yml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[⚠]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
header(){ echo -e "\n${CYAN}━━━ $1 ━━━${NC}\n"; }

# Load .env for LOCALSTACK_AUTH_TOKEN
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Preflight
check_docker() {
    if ! command -v docker &>/dev/null; then
        error "Docker is not installed. See: https://docs.docker.com/get-docker/"
    fi
    if ! docker info &>/dev/null; then
        error "Docker daemon is not running. Start Docker first."
    fi
}

cmd_start() {
    check_docker
    header "Starting Development Dependencies"

    if [ -z "${LOCALSTACK_AUTH_TOKEN:-}" ]; then
        warn "LOCALSTACK_AUTH_TOKEN not set. LocalStack Pro features disabled."
        warn "Set it in .env or export it: export LOCALSTACK_AUTH_TOKEN=your-token"
    fi

    docker compose -f "$COMPOSE_FILE" up -d

    echo ""
    info "Services starting..."
    echo ""
    echo "  LocalStack:  http://localhost:4566  (AWS API gateway)"
    echo "  Prometheus:  http://localhost:9090"
    echo "  Jaeger UI:   http://localhost:16686"
    echo ""
    echo "  Check status:  ./scripts/setup_deps.sh status"
    echo "  View logs:     ./scripts/setup_deps.sh logs"
}

cmd_stop() {
    check_docker
    header "Stopping Development Dependencies"
    docker compose -f "$COMPOSE_FILE" down
    info "All services stopped."
}

cmd_status() {
    check_docker
    header "Service Status"
    docker compose -f "$COMPOSE_FILE" ps
}

cmd_logs() {
    check_docker
    docker compose -f "$COMPOSE_FILE" logs -f --tail=50
}

cmd_clean() {
    check_docker
    header "Cleaning Up (stop + remove volumes)"
    docker compose -f "$COMPOSE_FILE" down -v
    info "All services stopped and volumes removed."
}

cmd_health() {
    check_docker
    header "Health Checks"

    local all_healthy=true

    # LocalStack
    if curl -sf http://localhost:4566/_localstack/health >/dev/null 2>&1; then
        info "LocalStack:   healthy"
    else
        warn "LocalStack:   not reachable"
        all_healthy=false
    fi

    # Prometheus
    if curl -sf http://localhost:9090/-/healthy >/dev/null 2>&1; then
        info "Prometheus:   healthy"
    else
        warn "Prometheus:   not reachable"
        all_healthy=false
    fi

    # Jaeger
    if curl -sf http://localhost:16686/ >/dev/null 2>&1; then
        info "Jaeger:       healthy"
    else
        warn "Jaeger:       not reachable"
        all_healthy=false
    fi

    echo ""
    if [ "$all_healthy" = true ]; then
        info "All services healthy!"
    else
        warn "Some services are not reachable. Run: ./scripts/setup_deps.sh start"
    fi
}

cmd_help() {
    cat <<'EOF'
🐳 SRE Agent — External Dependencies Manager

Usage:  ./scripts/setup_deps.sh <command>

Commands:
  start    Start all dependency services (LocalStack, Prometheus, Jaeger)
  stop     Stop all services
  status   Show running containers and their status
  logs     Tail logs from all services
  clean    Stop services and remove Docker volumes
  health   Check health endpoints of all services
  help     Show this message

Prerequisites:
  - Docker Engine + Docker Compose v2
  - LOCALSTACK_AUTH_TOKEN in .env (for LocalStack Pro features)
EOF
}

# Dispatch
COMMAND="${1:-help}"

case "$COMMAND" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    logs)    cmd_logs ;;
    clean)   cmd_clean ;;
    health)  cmd_health ;;
    help|--help|-h) cmd_help ;;
    *)       error "Unknown command: $COMMAND. Run './scripts/setup_deps.sh help'" ;;
esac
