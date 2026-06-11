#!/bin/bash
# Build and export Graphiti MCP Server Docker image for offline deployment
# Run this script on a build machine with network access.
#
# Two deployment modes:
#   Mode A (recommended): Build full image on external machine → export tar → transfer to internal network
#   Mode B: Export base image separately → transfer to internal network → build there
#
# Usage:
#   ./build-and-export.sh [OUTPUT_DIR] [MODE]
#
# Arguments:
#   OUTPUT_DIR  - Directory for exported files (default: ../dist)
#   MODE        - "full" (build + export final image) or "base" (export base image only)
#                Default: "full"
#
# Options (environment variables):
#   PIP_INDEX_URL      - Internal pip mirror URL (optional)
#   PIP_TRUSTED_HOST   - Trusted host for pip mirror (optional)
#   TARGET_PLATFORM    - Target platform, e.g. linux/amd64 (default: linux/amd64)
#
# Examples:
#   # Mode A: Build on external machine with internet
#   ./build-and-export.sh
#   # Then transfer mcp_server/dist/ to internal network and run:
#   #   docker load -i mcp_server/dist/graphiti-mcp-standalone.tar
#
#   # Mode B: Export base image for internal network build
#   ./build-and-export.sh ../dist base
#   # Then on internal network:
#   #   docker load -i mcp_server/dist/python-3.11-slim-bookworm-amd64.tar
#   #   docker build -f mcp_server/docker/Dockerfile.standalone -t graphiti-mcp-standalone:latest .

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT_DIR="${1:-${SCRIPT_DIR}/../dist}"
MODE="${2:-full}"
TARGET_PLATFORM="${TARGET_PLATFORM:-linux/amd64}"
BASE_IMAGE="python:3.11-slim-bookworm"

IMAGE_NAME="graphiti-mcp-standalone"
IMAGE_TAG="latest"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

mkdir -p "${OUTPUT_DIR}"

echo "========================================================"
echo "  Graphiti MCP Server - Docker Image Build & Export"
echo "  Target platform: ${TARGET_PLATFORM}"
echo "  Mode: ${MODE}"
echo "========================================================"

# --- Pull base image for target platform ---
echo ""
echo "[prep] Pulling base image: ${BASE_IMAGE} (${TARGET_PLATFORM})..."
docker pull --platform "${TARGET_PLATFORM}" "${BASE_IMAGE}"
echo "  Base image pulled."

if [ "${MODE}" = "base" ]; then
    # --- Mode B: Export base image only ---
    echo ""
    echo "[export] Exporting base image only (for internal network build)..."

    BASE_OUTPUT="${OUTPUT_DIR}/python-3.11-slim-bookworm-amd64.tar"
    docker save --platform "${TARGET_PLATFORM}" "${BASE_IMAGE}" -o "${BASE_OUTPUT}"

    echo "  Base image exported to: ${BASE_OUTPUT}"
    echo ""
    echo "========================================================"
    echo "  Mode B: Base image export complete!"
    echo "  Base image size: $(du -sh "${BASE_OUTPUT}" | cut -f1)"
    echo ""
    echo "  Next steps on internal network machine:"
    echo "    1. Transfer mcp_server/ directory + dist/ to internal network"
    echo "    2. On target: docker load -i ${BASE_OUTPUT}"
    echo "    3. On target: configure PIP_INDEX_URL and PIP_TRUSTED_HOST"
    echo "    4. On target: docker build --platform ${TARGET_PLATFORM} \\"
    echo "         --build-arg PIP_INDEX_URL=http://your-internal-mirror/simple \\"
    echo "         --build-arg PIP_TRUSTED_HOST=your-internal-mirror \\"
    echo "         -f mcp_server/docker/Dockerfile.standalone \\"
    echo "         -t ${FULL_IMAGE} ."
    echo "    5. On target: docker compose --profile mcp-server up -d"
    echo "========================================================"
    exit 0
fi

# --- Mode A: Build full image and export ---
echo ""
echo "[1/3] Building Docker image: ${FULL_IMAGE} (${TARGET_PLATFORM})..."

BUILD_ARGS="--platform ${TARGET_PLATFORM}"
if [ -n "${PIP_INDEX_URL}" ]; then
    BUILD_ARGS="${BUILD_ARGS} --build-arg PIP_INDEX_URL=${PIP_INDEX_URL}"
    echo "  Using pip mirror: ${PIP_INDEX_URL}"
fi
if [ -n "${PIP_TRUSTED_HOST}" ]; then
    BUILD_ARGS="${BUILD_ARGS} --build-arg PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}"
    echo "  Trusted host: ${PIP_TRUSTED_HOST}"
fi

docker build \
    ${BUILD_ARGS} \
    -f "${PROJECT_ROOT}/mcp_server/docker/Dockerfile.standalone" \
    -t "${FULL_IMAGE}" \
    "${PROJECT_ROOT}"

echo "  Image built successfully."

# --- Step 2: Verify image architecture ---
echo ""
echo "[2/3] Verifying image architecture..."

IMAGE_ARCH=$(docker inspect "${FULL_IMAGE}" --format '{{.Architecture}}')
IMAGE_OS=$(docker inspect "${FULL_IMAGE}" --format '{{.Os}}')
echo "  Architecture: ${IMAGE_OS}/${IMAGE_ARCH}"

if [ "${IMAGE_OS}" != "linux" ] || [ "${IMAGE_ARCH}" != "amd64" ]; then
    echo "  WARNING: Image architecture is ${IMAGE_OS}/${IMAGE_ARCH}, not linux/amd64!"
    echo "  The image may not run on CentOS 8 x86_64."
fi

# --- Step 3: Export image ---
echo ""
echo "[3/3] Exporting image to tar file..."

OUTPUT_FILE="${OUTPUT_DIR}/${IMAGE_NAME}-${IMAGE_TAG}.tar"
docker save "${FULL_IMAGE}" -o "${OUTPUT_FILE}"

echo "  Exported to: ${OUTPUT_FILE}"
echo ""
echo "========================================================"
echo "  Build complete!"
echo "  Image: ${FULL_IMAGE} (${IMAGE_OS}/${IMAGE_ARCH})"
echo "  File:  ${OUTPUT_FILE}"
echo "  Size:  $(du -sh "${OUTPUT_FILE}" | cut -f1)"
echo ""
echo "  Next steps on internal network machine:"
echo "    1. Transfer mcp_server/ directory + dist/ to internal network"
echo "    2. On target: docker load -i ${OUTPUT_FILE}"
echo "    3. On target: configure .env file"
echo "    4. On target: docker compose --profile mcp-server up -d"
echo "========================================================"