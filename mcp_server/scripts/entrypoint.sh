#!/bin/bash
# Graphiti MCP Server Entrypoint with Preflight Checks
# Runs preflight checks before starting the MCP server.
# If any check FAILs, the container exits with code 1.

set -e

echo "[preflight] ============================================"
echo "[preflight] Running pre-flight checks..."
echo "[preflight] ============================================"

/app/mcp/.venv/bin/python /app/mcp/scripts/preflight_check.py
PREFLIGHT_EXIT_CODE=$?

if [ $PREFLIGHT_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[preflight] ============================================"
    echo "[preflight] Pre-flight checks FAILED (exit code: $PREFLIGHT_EXIT_CODE)"
    echo "[preflight] MCP Server will NOT start."
    echo "[preflight] Please check the errors above and verify your .env configuration."
    echo "[preflight] ============================================"
    exit 1
fi

echo ""
echo "[preflight] ============================================"
echo "[preflight] All pre-flight checks PASSED."
echo "[preflight] Starting MCP Server..."
echo "[preflight] ============================================"
echo ""

exec /app/mcp/.venv/bin/python main.py
