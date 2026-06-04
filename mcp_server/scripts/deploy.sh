#!/bin/bash
# Deploy Graphiti MCP Server on Oracle Linux x86_64
# Run this script on the target machine after loading the Docker image.
#
# Prerequisites:
#   - Docker and Docker Compose V2 installed
#   - Docker image loaded (docker load -i graphiti-mcp-standalone-oracle.tar)
#   - PostgreSQL AGE database running and accessible
#   - .env file configured in mcp_server/docker/.env
#
# Usage:
#   ./deploy.sh [ACTION]
#
# Actions:
#   start   - Start MCP Server (default)
#   stop    - Stop MCP Server
#   status  - Check service status
#   logs    - Follow logs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${MCP_DIR}/docker/docker-compose-standalone.yml"
ENV_FILE="${MCP_DIR}/docker/.env"

ACTION="${1:-start}"

# --- Check prerequisites ---
check_prereqs() {
    echo "[check] Verifying prerequisites..."

    # Docker
    if ! command -v docker &> /dev/null; then
        echo "[check] ERROR: Docker is not installed."
        exit 1
    fi
    echo "[check]   Docker: $(docker --version)"

    # Docker Compose V2
    if ! docker compose version &> /dev/null; then
        echo "[check] ERROR: Docker Compose V2 is not installed."
        echo "[check]   Install: dnf install docker-compose-plugin"
        exit 1
    fi
    echo "[check]   Compose: $(docker compose version)"

    # Image
    if ! docker images graphiti-mcp-standalone:oracle &> /dev/null | grep -q graphiti; then
        echo "[check] ERROR: Image 'graphiti-mcp-standalone:oracle' not found."
        echo "[check]   Run: docker load -i graphiti-mcp-standalone-oracle.tar"
        exit 1
    fi
    echo "[check]   Image: graphiti-mcp-standalone:oracle (found)"

    # .env file
    if [ ! -f "${ENV_FILE}" ]; then
        echo "[check] ERROR: .env file not found at ${ENV_FILE}"
        echo "[check]   Copy from .env.example and edit with actual values:"
        echo "[check]   cp ${ENV_FILE}.example ${ENV_FILE}"
        exit 1
    fi
    echo "[check]   Config: ${ENV_FILE} (found)"

    # Validate critical env vars
    source "${ENV_FILE}"
    if [ -z "${POSTGRES_AGE_DSN}" ] || [ "${POSTGRES_AGE_DSN}" = "postgresql://graphiti:graphiti@your-pg-host:5432/graphiti" ]; then
        echo "[check] WARNING: POSTGRES_AGE_DSN appears to be unconfigured."
    fi
    if [ -z "${OPENAI_API_KEY}" ] || [ "${OPENAI_API_KEY}" = "your-internal-api-key" ]; then
        echo "[check] WARNING: OPENAI_API_KEY appears to be unconfigured."
    fi

    echo "[check] Prerequisites OK."
}

# --- Actions ---
do_start() {
    check_prereqs
    echo ""
    echo "[deploy] Starting Graphiti MCP Server..."
    cd "${MCP_DIR}"
    docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d

    echo ""
    echo "[deploy] Waiting for preflight checks and startup..."
    echo "[deploy] View logs: docker compose -f ${COMPOSE_FILE} logs -f graphiti-mcp"
    echo ""

    # Wait for health check
    echo "[deploy] Waiting for health check..."
    for i in $(seq 1 20); do
        if curl -sf http://localhost:${MCP_PORT:-8800}/health > /dev/null 2>&1; then
            echo "[deploy] MCP Server is healthy!"
            echo "[deploy] Endpoint: http://localhost:${MCP_PORT:-8800}/mcp/"
            return 0
        fi
        sleep 3
    done
    echo "[deploy] Health check timeout. Check logs:"
    echo "[deploy]   docker compose -f ${COMPOSE_FILE} logs graphiti-mcp"
    return 1
}

do_stop() {
    echo "[deploy] Stopping Graphiti MCP Server..."
    cd "${MCP_DIR}"
    docker compose -f "${COMPOSE_FILE}" down
    echo "[deploy] Stopped."
}

do_status() {
    cd "${MCP_DIR}"
    docker compose -f "${COMPOSE_FILE}" ps
}

do_logs() {
    cd "${MCP_DIR}"
    docker compose -f "${COMPOSE_FILE}" logs -f graphiti-mcp
}

# --- Main ---
case "${ACTION}" in
    start)
        do_start
        ;;
    stop)
        do_stop
        ;;
    status)
        do_status
        ;;
    logs)
        do_logs
        ;;
    *)
        echo "Usage: $0 {start|stop|status|logs}"
        exit 1
        ;;
esac
