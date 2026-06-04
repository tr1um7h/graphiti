#!/bin/bash
# Build and export Graphiti MCP Server Docker image for Oracle Linux x86_64
# Run this script on a build machine with network access.
#
# Usage:
#   ./build-and-export.sh [OUTPUT_DIR]
#
# Options:
#   PIP_INDEX_URL      - Internal pip mirror URL (env var, optional)
#   PIP_TRUSTED_HOST   - Trusted host for pip mirror (env var, optional)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT_DIR="${1:-${SCRIPT_DIR}/../dist}"

mkdir -p "${OUTPUT_DIR}"

IMAGE_NAME="graphiti-mcp-standalone"
IMAGE_TAG="oracle"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo "========================================================"
echo "  Graphiti MCP Server - Docker Image Build & Export"
echo "  Target: Oracle Linux x86_64 offline deployment"
echo "========================================================"

# --- Step 1: Build Docker image ---
echo ""
echo "[1/2] Building Docker image: ${FULL_IMAGE}..."

BUILD_ARGS=""
if [ -n "${PIP_INDEX_URL}" ]; then
    BUILD_ARGS="${BUILD_ARGS} --build-arg PIP_INDEX_URL=${PIP_INDEX_URL}"
    echo "  Using pip mirror: ${PIP_INDEX_URL}"
fi
if [ -n "${PIP_TRUSTED_HOST}" ]; then
    BUILD_ARGS="${BUILD_ARGS} --build-arg PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}"
    echo "  Trusted host: ${PIP_TRUSTED_HOST}"
fi

docker build \
    -f "${PROJECT_ROOT}/mcp_server/docker/Dockerfile.oracle" \
    -t "${FULL_IMAGE}" \
    ${BUILD_ARGS} \
    "${PROJECT_ROOT}"

echo "  Image built successfully."

# --- Step 2: Export image ---
echo ""
echo "[2/2] Exporting image to tar file..."

OUTPUT_FILE="${OUTPUT_DIR}/${IMAGE_NAME}-${IMAGE_TAG}.tar"
docker save "${FULL_IMAGE}" -o "${OUTPUT_FILE}"

echo "  Exported to: ${OUTPUT_FILE}"
echo ""
echo "========================================================"
echo "  Build complete!"
echo "  Image size: $(du -sh "${OUTPUT_FILE}" | cut -f1)"
echo "  "
echo "  Next steps:"
echo "    1. Transfer the entire mcp_server/ directory to target machine"
echo "    2. On target: docker load -i ${OUTPUT_FILE}"
echo "    3. On target: configure mcp_server/docker/.env"
echo "    4. On target: docker compose -f docker-compose-standalone.yml up -d"
echo "========================================================"
