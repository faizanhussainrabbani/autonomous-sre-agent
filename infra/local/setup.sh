#!/usr/bin/env bash
# ===========================================================================
# Local eBPF Development Environment Setup
#
# Creates: Colima VM → k3d cluster → OTel Collector → Pixie → Sample services
# Targets: AC-2.2.1 through AC-2.2.4 local validation
#
# Prerequisites: Homebrew installed
# Usage: ./infra/local/setup.sh
# ===========================================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ===========================================================================
# Step 1: Install prerequisites
# ===========================================================================

info "Step 1/6: Checking prerequisites..."

install_if_missing() {
    local cmd=$1
    local install_cmd=$2
    if ! command -v "$cmd" &>/dev/null; then
        info "Installing $cmd..."
        eval "$install_cmd"
    else
        info "✓ $cmd already installed"
    fi
}

install_if_missing "colima" "brew install colima"
install_if_missing "docker" "brew install docker"
install_if_missing "kubectl" "brew install kubectl"
install_if_missing "k3d" "brew install k3d"
install_if_missing "helm" "brew install helm"

# Pixie CLI
if ! command -v px &>/dev/null; then
    info "Installing Pixie CLI..."
    bash -c "$(curl -fsSL https://withpixie.ai/install.sh)"
else
    info "✓ Pixie CLI already installed"
fi

# ===========================================================================
# Step 2: Start Colima VM with eBPF-capable kernel
# ===========================================================================

info "Step 2/6: Starting Colima VM..."

if colima status 2>/dev/null | grep -q "Running"; then
    info "✓ Colima already running"
else
    colima start \
        --cpu 4 \
        --memory 8 \
        --disk 40 \
        --vm-type vz \
        --mount-type virtiofs \
        --kubernetes
    info "✓ Colima started with eBPF-capable Linux kernel"
fi

# Verify eBPF support in the VM
info "Verifying eBPF support..."
if colima ssh -- ls /sys/kernel/btf/vmlinux &>/dev/null; then
    info "✓ BTF (BPF Type Format) available — eBPF CO-RE supported"
else
    warn "BTF not available. Some eBPF features may be limited."
fi

# ===========================================================================
# Step 3: Create k3d cluster
# ===========================================================================

info "Step 3/6: Creating k3d cluster..."

CLUSTER_NAME="sre-local"

if k3d cluster list 2>/dev/null | grep -q "$CLUSTER_NAME"; then
    info "✓ Cluster '$CLUSTER_NAME' already exists"
else
    k3d cluster create "$CLUSTER_NAME" \
        --agents 2 \
        --port "8080:80@loadbalancer" \
        --port "4317:4317@loadbalancer" \
        --port "4318:4318@loadbalancer" \
        --wait
    info "✓ k3d cluster '$CLUSTER_NAME' created with 2 worker nodes"
fi

kubectl config use-context "k3d-${CLUSTER_NAME}"
kubectl cluster-info

# ===========================================================================
# Step 4: Deploy OTel Collector
# ===========================================================================

info "Step 4/6: Deploying OpenTelemetry Collector..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

kubectl apply -f "$PROJECT_ROOT/infra/k8s/otel-collector.yaml"
kubectl -n observability wait --for=condition=available deployment/otel-collector --timeout=120s || \
    warn "OTel Collector not ready yet — check with: kubectl -n observability get pods"

info "✓ OTel Collector deployed"

# ===========================================================================
# Step 5: Deploy Pixie
# ===========================================================================

info "Step 5/6: Deploying Pixie..."

if kubectl get namespace px-operator &>/dev/null 2>&1; then
    info "✓ Pixie already deployed"
else
    if px auth status &>/dev/null 2>&1; then
        px deploy --cluster_name="$CLUSTER_NAME" --wait
        info "✓ Pixie deployed"
    else
        warn "Pixie not authenticated. Run 'px auth login' first."
        warn "Skipping Pixie deployment. You can deploy later with:"
        echo "    px auth login"
        echo "    px deploy --cluster_name=$CLUSTER_NAME"
    fi
fi

# ===========================================================================
# Step 6: Deploy sample microservices
# ===========================================================================

info "Step 6/6: Deploying sample microservices..."

kubectl apply -f "$PROJECT_ROOT/infra/k8s/sample-services.yaml"
kubectl -n default wait --for=condition=available deployment/svc-a --timeout=120s || \
    warn "Sample services not ready yet — check with: kubectl get pods"

info "✓ Sample microservices deployed (svc-a → svc-b → svc-c)"

# ===========================================================================
# Summary
# ===========================================================================

echo ""
echo "==========================================="
echo " eBPF Local Dev Environment Ready"
echo "==========================================="
echo ""
echo " Cluster:        k3d-${CLUSTER_NAME}"
echo " OTel OTLP:      localhost:4317 (gRPC), :4318 (HTTP)"
echo " Sample services: svc-a → svc-b → svc-c"
echo ""
echo " Useful commands:"
echo "   kubectl get pods -A              # see all pods"
echo "   px run px/cluster                # pixie cluster status"
echo "   px run px/syscalls               # view syscall data"
echo "   px run px/network_stats          # view network flows"
echo "   colima ssh                       # SSH into Linux VM"
echo ""
echo " Teardown: ./infra/local/teardown.sh"
echo "==========================================="
