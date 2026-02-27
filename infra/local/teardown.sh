#!/usr/bin/env bash
# ===========================================================================
# Teardown local eBPF development environment
# ===========================================================================

set -euo pipefail

GREEN='\033[0;32m'
NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC} $1"; }

CLUSTER_NAME="sre-local"

info "Deleting k3d cluster '$CLUSTER_NAME'..."
k3d cluster delete "$CLUSTER_NAME" 2>/dev/null || true

info "Stopping Colima..."
colima stop 2>/dev/null || true

info "✓ Local eBPF environment torn down"
