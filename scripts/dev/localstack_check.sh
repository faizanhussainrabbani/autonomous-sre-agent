#!/usr/bin/env bash
# ===========================================================================
# SRE Agent — LocalStack Pro Readiness Check
#
# Validates that LocalStack Pro is running with the correct image, edition,
# and all required services before integration tests or demos execute.
#
# Usage:
#   ./scripts/dev/localstack_check.sh            Basic readiness check
#   ./scripts/dev/localstack_check.sh --deep      Also smoke-test Lambda execution
#
# Exit codes:
#   0  All checks passed
#   1  One or more checks failed (diagnostic output printed)
#
# Reference: docs/testing/localstack_pro_usage_standard.md
# ===========================================================================

set -euo pipefail

LOCALSTACK_HEALTH_URL="${LOCALSTACK_ENDPOINT:-http://localhost:4566}/_localstack/health"
LOCALSTACK_ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
LOCALSTACK_REQUIRED_SERVICES="autoscaling,cloudwatch,ec2,ecs,events,iam,lambda,logs,s3,secretsmanager,sns,sts"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[⚠]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }
header(){ echo -e "\n${CYAN}━━━ $1 ━━━${NC}\n"; }

DEEP=false
if [ "${1:-}" = "--deep" ]; then
    DEEP=true
fi

header "LocalStack Pro Readiness Check"

FAILED=false

# ── Check 1: Container running with Pro image ────────────────────────────
IMAGE="$(docker ps --filter name='^localstack$' --format '{{.Image}}' 2>/dev/null | head -n 1)"

if [ -z "$IMAGE" ]; then
    error "LocalStack container is not running"
    echo "  Start it with: bash scripts/dev/setup_deps.sh start"
    exit 1
fi

if echo "$IMAGE" | grep -q '^localstack/localstack-pro'; then
    info "Container image: $IMAGE"
else
    error "Container image is not Pro: $IMAGE"
    echo "  Expected: localstack/localstack-pro:latest"
    FAILED=true
fi

# ── Check 2: Health endpoint reachable ───────────────────────────────────
HEALTH_JSON="$(curl -sf "$LOCALSTACK_HEALTH_URL" 2>/dev/null)" || {
    error "Health endpoint unreachable at $LOCALSTACK_HEALTH_URL"
    echo "  Container may still be starting. Wait and retry."
    exit 1
}

# ── Check 3: Pro edition ─────────────────────────────────────────────────
EDITION="$(echo "$HEALTH_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('edition',''))" 2>/dev/null)"

if [ "$EDITION" = "pro" ]; then
    info "Edition: pro"
else
    error "Edition is '$EDITION', expected 'pro'"
    echo "  Check LOCALSTACK_AUTH_TOKEN is valid and not expired."
    FAILED=true
fi

# ── Check 4: Required services ───────────────────────────────────────────
VALIDATION="$(python3 -c '
import json
import sys

required = [
    "autoscaling",
    "cloudwatch",
    "ec2",
    "ecs",
    "events",
    "iam",
    "lambda",
    "logs",
    "s3",
    "secretsmanager",
    "sns",
    "sts",
]

payload = json.load(sys.stdin)
services = payload.get("services") or {}
ready = []
missing = []
for name in required:
    status = str(services.get(name, "")).lower()
    if status in {"available", "running"}:
        ready.append(name)
    else:
        missing.append(f"{name}({status or 'absent'})")

print(f"ready={len(ready)}/{len(required)}")
if missing:
    print("missing=" + ",".join(missing))
    raise SystemExit(1)
' <<<"$HEALTH_JSON" 2>&1)" || {
    error "Service validation failed"
    echo "  $VALIDATION"
    echo "  Required: $LOCALSTACK_REQUIRED_SERVICES"
    FAILED=true
}

if [ "$FAILED" = false ]; then
    READY_COUNT="$(echo "$VALIDATION" | head -1)"
    info "Services: $READY_COUNT"
fi

# ── Check 5 (optional): Lambda smoke test ────────────────────────────────
if [ "$DEEP" = true ]; then
    header "Deep Check: Lambda Runtime Smoke Test"

    LAMBDA_RESULT="$(python3 - "$LOCALSTACK_ENDPOINT" <<'PY'
import boto3
import io
import json
import sys
import time
import zipfile

endpoint = sys.argv[1]
kw = dict(
    endpoint_url=endpoint,
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",
)
lc = boto3.client("lambda", **kw)
fname = "_localstack_check_probe"

try:
    lc.delete_function(FunctionName=fname)
except Exception:
    pass

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr(
        "lambda_function.py",
        'def handler(event, context): return {"statusCode": 200, "body": "ok"}',
    )
buf.seek(0)

lc.create_function(
    FunctionName=fname,
    Runtime="python3.11",
    Handler="lambda_function.handler",
    Role="arn:aws:iam::000000000000:role/probe-role",
    Code={"ZipFile": buf.read()},
    Timeout=30,
)

for _ in range(30):
    state = lc.get_function(FunctionName=fname)["Configuration"]["State"]
    if state == "Active":
        break
    time.sleep(5)
else:
    lc.delete_function(FunctionName=fname)
    print("TIMEOUT:function stuck in Pending state after 150s")
    raise SystemExit(1)

start = time.time()
resp = lc.invoke(FunctionName=fname, Payload=json.dumps({"probe": True}))
elapsed = time.time() - start
payload = json.loads(resp["Payload"].read())
lc.delete_function(FunctionName=fname)

if payload.get("statusCode") == 200:
    print(f"OK:{elapsed:.1f}s")
else:
    print(f"UNEXPECTED:{json.dumps(payload)}")
    raise SystemExit(2)
PY
)" || {
        error "Lambda smoke test failed: $LAMBDA_RESULT"
        echo "  Check LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT and Docker socket mount."
        FAILED=true
    }

    if [ "$FAILED" = false ]; then
        LAMBDA_TIME="$(echo "$LAMBDA_RESULT" | grep '^OK:' | cut -d: -f2)"
        info "Lambda invocation succeeded in $LAMBDA_TIME"
    fi
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
if [ "$FAILED" = true ]; then
    error "One or more checks failed. Fix issues above before running tests or demos."
    exit 1
else
    info "All checks passed — LocalStack Pro is ready."
    exit 0
fi
