#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/lambda-demo"
PACKAGE="$ROOT_DIR/build/fleet-health-orchestrator-lambda.zip"

rm -rf "$BUILD_DIR" "$PACKAGE"
mkdir -p "$BUILD_DIR" "$(dirname "$PACKAGE")"

python3 -m pip install --target "$BUILD_DIR" "$ROOT_DIR/services/orchestrator"

(
  cd "$BUILD_DIR"
  zip -qr "$PACKAGE" .
)

echo "$PACKAGE"
