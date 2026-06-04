#!/usr/bin/env python3
"""Graphiti MCP Server Pre-flight Check Script.

Validates that all three core dependencies are available and compatible
with Graphiti before the MCP Server starts:

  1. PostgreSQL AGE database: connection, extensions, schema creation
  2. Embedding model API: endpoint accessibility, response format, vector dimensions
  3. LLM provider API: endpoint accessibility, chat completions, structured output

Usage:
  # Load config from .env file (searched upward from script location)
  python preflight_check.py

  # Use environment variables directly
  export POSTGRES_AGE_DSN=postgresql://graphiti:graphiti@localhost:55432/graphiti
  export OPENAI_API_KEY=your-key
  export OPENAI_BASE_URL=http://your-llm-endpoint/v1
  export EMBEDDING_API_URL=http://your-embedding-endpoint/v1
  python preflight_check.py

Exit codes:
  0 - All critical checks passed (WARN is acceptable)
  1 - At least one check FAILED
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx


# ======================================================================
# Configuration
# ======================================================================


def load_env_from_file():
    """Load environment variables from .env file (does not override existing)."""
    # Search upward from script location for .env file
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir, *script_dir.parents]:
        env_path = parent / '.env'
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' not in line:
                        continue
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = value
            return


class TestConfig:
    """Test configuration loaded from environment variables."""

    def __init__(self):
        # Database
        self.POSTGRES_AGE_DSN = os.environ.get(
            'POSTGRES_AGE_DSN', 'postgresql://graphiti:graphiti@localhost:55432/graphiti'
        )
        self.POSTGRES_AGE_GRAPH_NAME = os.environ.get('POSTGRES_AGE_GRAPH_NAME', 'graphiti')
        self.POSTGRES_AGE_EMBEDDING_DIMENSION = int(
            os.environ.get('POSTGRES_AGE_EMBEDDING_DIMENSION', '384')
        )
        # LLM
        self.OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
        self.OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', '')
        self.OPENAI_MODEL_NAME = os.environ.get('OPENAI_MODEL_NAME', 'MiniMax-M2.7')
        # Embedding
        self.EMBEDDING_API_URL = os.environ.get('EMBEDDING_API_URL', '')
        self.EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
        self.EMBEDDING_DIM = int(os.environ.get('EMBEDDING_DIM', '384'))


# ======================================================================
# Result tracking
# ======================================================================


class TestResult:
    PASS = 'PASS'
    FAIL = 'FAIL'
    WARN = 'WARN'
    SKIP = 'SKIP'

    def __init__(self):
        self.results: list[dict] = []
        self._has_fail = False

    def record(self, suite: str, name: str, status: str, detail: str = '', duration_ms: float = 0):
        self.results.append({
            'suite': suite,
            'name': name,
            'status': status,
            'detail': detail,
            'duration_ms': round(duration_ms, 1),
        })
        if status == self.FAIL:
            self._has_fail = True
        icon = {
            self.PASS: '[PASS]',
            self.FAIL: '[FAIL]',
            self.WARN: '[WARN]',
            self.SKIP: '[SKIP]',
        }[status]
        detail_str = f' - {detail}' if detail else ''
        print(f'  {icon} {name} ({duration_ms:.0f}ms){detail_str}')

    @property
    def has_failure(self):
        return self._has_fail

    def summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r['status'] == self.PASS)
        failed = sum(1 for r in self.results if r['status'] == self.FAIL)
        warned = sum(1 for r in self.results if r['status'] == self.WARN)
        skipped = sum(1 for r in self.results if r['status'] == self.SKIP)
        print(f'\n{"=" * 60}')
        print(f'  Total: {total}  |  Pass: {passed}  |  Fail: {failed}'
              f'  |  Warn: {warned}  |  Skip: {skipped}')
        print(f'{"=" * 60}')
        return not self._has_fail


# ======================================================================
# Test 1: PostgreSQL AGE Database
# ======================================================================


async def test_postgres_age(config: TestConfig, result: TestResult):
    """Test PostgreSQL AGE database for full Graphiti compatibility."""
    suite = 'PostgreSQL AGE'
    print(f'\n{"=" * 60}')
    print(f'  Suite: {suite}')
    print(f'  DSN: {_mask_dsn(config.POSTGRES_AGE_DSN)}')
    print(f'{"=" * 60}')

    try:
        from pgvector.psycopg import register_vector_async
        from psycopg import AsyncConnection
    except ImportError:
        result.record(suite, 'Python dependencies', TestResult.FAIL,
                      'psycopg/pgvector not installed. Run: pip install "psycopg[binary,pool]" pgvector')
        return

    # --- 1.1 Database connection ---
    t0 = time.monotonic()
    try:
        conn = await AsyncConnection.connect(config.POSTGRES_AGE_DSN)
        await conn.close()
        result.record(suite, 'Database connection', TestResult.PASS, '', (time.monotonic() - t0) * 1000)
    except Exception as e:
        result.record(suite, 'Database connection', TestResult.FAIL, str(e), (time.monotonic() - t0) * 1000)
        return  # Cannot proceed without connection

    async with await AsyncConnection.connect(config.POSTGRES_AGE_DSN) as conn:
        # --- 1.2 Required extensions ---
        required_extensions = ['age', 'vector', 'pg_trgm']
        for ext_name in required_extensions:
            t0 = time.monotonic()
            try:
                await conn.execute(f'CREATE EXTENSION IF NOT EXISTS {ext_name}')
                await conn.commit()
                cur = await conn.execute(
                    'SELECT 1 FROM pg_extension WHERE extname = %s', (ext_name,)
                )
                row = await cur.fetchone()
                if row:
                    result.record(suite, f'Extension: {ext_name}', TestResult.PASS,
                                  '', (time.monotonic() - t0) * 1000)
                else:
                    result.record(suite, f'Extension: {ext_name}', TestResult.FAIL,
                                  'CREATE EXTENSION executed but extension not found',
                                  (time.monotonic() - t0) * 1000)
            except Exception as e:
                result.record(suite, f'Extension: {ext_name}', TestResult.FAIL,
                              str(e), (time.monotonic() - t0) * 1000)

        # --- 1.3 AGE load + search_path ---
        t0 = time.monotonic()
        try:
            await register_vector_async(conn)
            await conn.execute("LOAD 'age'")
            await conn.execute('SET search_path = public, ag_catalog, "$user", public')
            await conn.commit()
            result.record(suite, 'AGE load + search_path', TestResult.PASS,
                          '', (time.monotonic() - t0) * 1000)
        except Exception as e:
            result.record(suite, 'AGE load + search_path', TestResult.FAIL,
                          str(e), (time.monotonic() - t0) * 1000)

        # --- 1.4 AGE graph creation ---
        graph_name = f'graphiti_preflight_{int(time.time())}'
        t0 = time.monotonic()
        try:
            # Clean up if exists
            cur = await conn.execute(
                'SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s', (graph_name,)
            )
            if await cur.fetchone():
                await conn.execute('SELECT drop_graph(%s, true)', (graph_name,))
            # Create
            await conn.execute('SELECT create_graph(%s)', (graph_name,))
            await conn.commit()
            # Verify
            cur = await conn.execute(
                'SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s', (graph_name,)
            )
            if await cur.fetchone():
                result.record(suite, 'AGE graph creation', TestResult.PASS,
                              f'graph={graph_name}', (time.monotonic() - t0) * 1000)
            else:
                result.record(suite, 'AGE graph creation', TestResult.FAIL,
                              'create_graph executed but graph not found',
                              (time.monotonic() - t0) * 1000)
            # Cleanup
            await conn.execute('SELECT drop_graph(%s, true)', (graph_name,))
            await conn.commit()
        except Exception as e:
            result.record(suite, 'AGE graph creation', TestResult.FAIL,
                          str(e), (time.monotonic() - t0) * 1000)

        # --- 1.5 Schema: table with vector column ---
        t0 = time.monotonic()
        dim = config.POSTGRES_AGE_EMBEDDING_DIMENSION
        test_table = f'_preflight_test_{int(time.time())}'
        try:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {test_table} (
                    uuid text PRIMARY KEY,
                    group_id text NOT NULL,
                    name text NOT NULL,
                    name_embedding vector({dim}),
                    created_at timestamptz NOT NULL
                )
            """)
            await conn.commit()
            # Insert a test row with vector
            await conn.execute(
                f'INSERT INTO {test_table} (uuid, group_id, name, name_embedding, created_at) '
                f"VALUES ('test-uuid', 'test-group', 'test', "
                f"'[{','.join(['0.1'] * dim)}]'::vector, NOW())"
            )
            await conn.commit()
            result.record(suite, f'Schema: table + vector({dim}) column', TestResult.PASS,
                          '', (time.monotonic() - t0) * 1000)
            # Cleanup
            await conn.execute(f'DROP TABLE IF EXISTS {test_table}')
            await conn.commit()
        except Exception as e:
            result.record(suite, f'Schema: table + vector({dim}) column', TestResult.FAIL,
                          str(e), (time.monotonic() - t0) * 1000)
            try:
                await conn.execute(f'DROP TABLE IF EXISTS {test_table}')
                await conn.commit()
            except Exception:
                pass

        # --- 1.6 HNSW index ---
        t0 = time.monotonic()
        test_table = f'_preflight_hnsw_{int(time.time())}'
        try:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {test_table} (
                    uuid text PRIMARY KEY,
                    name_embedding vector({dim})
                )
            """)
            await conn.execute(f"""
                CREATE INDEX ON {test_table}
                USING hnsw (name_embedding vector_cosine_ops)
                WHERE name_embedding IS NOT NULL
            """)
            await conn.commit()
            result.record(suite, 'Index: HNSW (vector_cosine_ops)', TestResult.PASS,
                          '', (time.monotonic() - t0) * 1000)
            await conn.execute(f'DROP TABLE IF EXISTS {test_table}')
            await conn.commit()
        except Exception as e:
            result.record(suite, 'Index: HNSW (vector_cosine_ops)', TestResult.FAIL,
                          str(e), (time.monotonic() - t0) * 1000)
            try:
                await conn.execute(f'DROP TABLE IF EXISTS {test_table}')
                await conn.commit()
            except Exception:
                pass

        # --- 1.7 GIN full-text index ---
        t0 = time.monotonic()
        test_table = f'_preflight_gin_{int(time.time())}'
        try:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {test_table} (
                    uuid text PRIMARY KEY,
                    name text NOT NULL,
                    search_vector tsvector GENERATED ALWAYS AS (
                        setweight(to_tsvector('simple', coalesce(name, '')), 'A')
                    ) STORED
                )
            """)
            await conn.execute(f'CREATE INDEX ON {test_table} USING gin (search_vector)')
            await conn.commit()
            result.record(suite, 'Index: GIN (full-text search)', TestResult.PASS,
                          '', (time.monotonic() - t0) * 1000)
            await conn.execute(f'DROP TABLE IF EXISTS {test_table}')
            await conn.commit()
        except Exception as e:
            result.record(suite, 'Index: GIN (full-text search)', TestResult.FAIL,
                          str(e), (time.monotonic() - t0) * 1000)
            try:
                await conn.execute(f'DROP TABLE IF EXISTS {test_table}')
                await conn.commit()
            except Exception:
                pass


# ======================================================================
# Test 2: Embedding Model API
# ======================================================================


async def test_embedding(config: TestConfig, result: TestResult):
    """Test remote embedding API for OpenAI compatibility.

    Uses httpx directly instead of the OpenAI SDK because the SDK
    issues a /v1/models request first, which many custom embedding
    services don't implement.
    """
    suite = 'Embedding Model API'
    print(f'\n{"=" * 60}')
    print(f'  Suite: {suite}')
    print(f'  API URL: {config.EMBEDDING_API_URL or "(not set)"}')
    print(f'  Model: {config.EMBEDDING_MODEL}')
    print(f'{"=" * 60}')

    if not config.EMBEDDING_API_URL:
        result.record(suite, 'Configuration', TestResult.SKIP, 'EMBEDDING_API_URL not set')
        return

    # --- 2.1 Endpoint accessibility ---
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            resp = await http_client.post(
                f'{config.EMBEDDING_API_URL.rstrip("/")}/embeddings',
                json={'input': 'hello', 'model': config.EMBEDDING_MODEL},
            )
        resp.raise_for_status()
        data = resp.json()
        result.record(suite, 'Endpoint accessibility', TestResult.PASS,
                      '', (time.monotonic() - t0) * 1000)
    except Exception as e:
        result.record(suite, 'Endpoint accessibility', TestResult.FAIL,
                      str(e), (time.monotonic() - t0) * 1000)
        return

    # --- 2.2 Response format ---
    t0 = time.monotonic()
    try:
        assert 'data' in data, 'Response missing "data" field'
        assert len(data['data']) > 0, 'Response "data" is empty'
        assert 'embedding' in data['data'][0], 'Response missing "embedding" field'
        embedding = data['data'][0]['embedding']
        assert isinstance(embedding, list), f'embedding type error: {type(embedding)}'
        assert all(isinstance(x, float) for x in embedding), 'embedding contains non-float elements'
        result.record(suite, 'Response format (OpenAI compatible)', TestResult.PASS,
                      f'data_len={len(data["data"])}', (time.monotonic() - t0) * 1000)
    except AssertionError as e:
        result.record(suite, 'Response format (OpenAI compatible)', TestResult.FAIL,
                      str(e), (time.monotonic() - t0) * 1000)

    # --- 2.3 Vector dimensions ---
    t0 = time.monotonic()
    try:
        actual_dim = len(data['data'][0]['embedding'])
        expected_dim = config.EMBEDDING_DIM
        if actual_dim == expected_dim:
            result.record(suite, f'Vector dimensions (dim={actual_dim})', TestResult.PASS,
                          '', (time.monotonic() - t0) * 1000)
        else:
            result.record(suite, f'Vector dimensions', TestResult.WARN,
                          f'Expected={expected_dim}, Actual={actual_dim}. '
                          f'Update POSTGRES_AGE_EMBEDDING_DIMENSION to {actual_dim}',
                          (time.monotonic() - t0) * 1000)
    except Exception as e:
        result.record(suite, 'Vector dimensions', TestResult.FAIL,
                      str(e), (time.monotonic() - t0) * 1000)

    # --- 2.4 Batch embedding ---
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            batch_resp = await http_client.post(
                f'{config.EMBEDDING_API_URL.rstrip("/")}/embeddings',
                json={'input': ['hello world', 'test embedding'], 'model': config.EMBEDDING_MODEL},
            )
        batch_resp.raise_for_status()
        batch_data = batch_resp.json()
        if len(batch_data['data']) == 2:
            result.record(suite, 'Batch embedding (batch=2)', TestResult.PASS,
                          '', (time.monotonic() - t0) * 1000)
        else:
            result.record(suite, 'Batch embedding', TestResult.WARN,
                          f'Returned {len(batch_data["data"])} items, expected 2',
                          (time.monotonic() - t0) * 1000)
    except Exception as e:
        result.record(suite, 'Batch embedding', TestResult.WARN,
                      f'Batch request failed (non-critical): {e}',
                      (time.monotonic() - t0) * 1000)


# ======================================================================
# Test 3: LLM Provider API
# ======================================================================


async def test_llm(config: TestConfig, result: TestResult):
    """Test LLM API for OpenAI compatibility.

    Uses httpx directly to avoid the OpenAI SDK's /v1/models
    pre-flight request that custom endpoints may not support.
    """
    suite = 'LLM Provider API'
    print(f'\n{"=" * 60}')
    print(f'  Suite: {suite}')
    print(f'  Base URL: {config.OPENAI_BASE_URL or "(not set)"}')
    print(f'  Model: {config.OPENAI_MODEL_NAME}')
    print(f'{"=" * 60}')

    if not config.OPENAI_API_KEY:
        result.record(suite, 'Configuration', TestResult.SKIP, 'OPENAI_API_KEY not set')
        return
    if not config.OPENAI_BASE_URL:
        result.record(suite, 'Configuration', TestResult.SKIP, 'OPENAI_BASE_URL not set')
        return

    base_url = config.OPENAI_BASE_URL.rstrip('/')

    # --- 3.1 Endpoint accessibility ---
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            resp = await http_client.post(
                f'{base_url}/chat/completions',
                headers={'Authorization': f'Bearer {config.OPENAI_API_KEY}'},
                json={
                    'model': config.OPENAI_MODEL_NAME,
                    'messages': [{'role': 'user', 'content': 'Say OK'}],
                    'max_tokens': 10,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        result.record(suite, 'Endpoint accessibility (chat/completions)', TestResult.PASS,
                      '', (time.monotonic() - t0) * 1000)
    except Exception as e:
        result.record(suite, 'Endpoint accessibility (chat/completions)', TestResult.FAIL,
                      str(e), (time.monotonic() - t0) * 1000)
        return

    # --- 3.2 Response format ---
    t0 = time.monotonic()
    try:
        assert 'choices' in data, 'Response missing "choices" field'
        assert len(data['choices']) > 0, 'Response "choices" is empty'
        assert 'message' in data['choices'][0], 'Response missing "message" field'
        content = data['choices'][0]['message'].get('content', '')
        assert content, 'Response message.content is empty'
        result.record(suite, 'Response format (Chat Completions)', TestResult.PASS,
                      f'content={content[:50]}', (time.monotonic() - t0) * 1000)
    except AssertionError as e:
        result.record(suite, 'Response format (Chat Completions)', TestResult.FAIL,
                      str(e), (time.monotonic() - t0) * 1000)

    # --- 3.3 Structured output (JSON mode) ---
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            json_resp = await http_client.post(
                f'{base_url}/chat/completions',
                headers={'Authorization': f'Bearer {config.OPENAI_API_KEY}'},
                json={
                    'model': config.OPENAI_MODEL_NAME,
                    'messages': [{
                        'role': 'user',
                        'content': 'Return a JSON object with one key "status" set to "ok". Return only valid JSON.',
                    }],
                    'max_tokens': 50,
                    'response_format': {'type': 'json_object'},
                },
            )
        json_resp.raise_for_status()
        json_data = json_resp.json()
        content = json_data['choices'][0]['message']['content']
        json.loads(content)
        result.record(suite, 'Structured output (JSON mode)', TestResult.PASS,
                      '', (time.monotonic() - t0) * 1000)
    except json.JSONDecodeError as e:
        result.record(suite, 'Structured output (JSON mode)', TestResult.WARN,
                      f'JSON parse failed (LLM may not support json_object): {e}',
                      (time.monotonic() - t0) * 1000)
    except Exception as e:
        error_str = str(e)
        if 'response_format' in error_str.lower() or 'not support' in error_str.lower():
            result.record(suite, 'Structured output (JSON mode)', TestResult.WARN,
                          f'LLM does not support json_object mode: {error_str[:100]}',
                          (time.monotonic() - t0) * 1000)
        else:
            result.record(suite, 'Structured output (JSON mode)', TestResult.FAIL,
                          error_str[:200], (time.monotonic() - t0) * 1000)

    # --- 3.4 Multi-turn conversation ---
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            multi_resp = await http_client.post(
                f'{base_url}/chat/completions',
                headers={'Authorization': f'Bearer {config.OPENAI_API_KEY}'},
                json={
                    'model': config.OPENAI_MODEL_NAME,
                    'messages': [
                        {'role': 'system', 'content': 'You are a helpful assistant.'},
                        {'role': 'user', 'content': 'My name is TestUser.'},
                        {'role': 'assistant', 'content': 'Hello TestUser!'},
                        {'role': 'user', 'content': 'What is my name?'},
                    ],
                    'max_tokens': 20,
                },
            )
        multi_resp.raise_for_status()
        multi_data = multi_resp.json()
        content = multi_data['choices'][0]['message'].get('content', '')
        if 'testuser' in content.lower() or 'test' in content.lower():
            result.record(suite, 'Multi-turn context', TestResult.PASS,
                          f'response={content[:80]}', (time.monotonic() - t0) * 1000)
        else:
            result.record(suite, 'Multi-turn context', TestResult.WARN,
                          f'LLM may not use context correctly: {content[:80]}',
                          (time.monotonic() - t0) * 1000)
    except Exception as e:
        result.record(suite, 'Multi-turn context', TestResult.WARN,
                      str(e)[:100], (time.monotonic() - t0) * 1000)


# ======================================================================
# Utilities
# ======================================================================


def _mask_dsn(dsn: str) -> str:
    """Mask password in DSN for display."""
    if '@' in dsn and ':' in dsn.split('@')[0]:
        prefix, rest = dsn.rsplit('@', 1)
        if ':' in prefix:
            user_pass = prefix.rsplit(':', 1)[1]
            return dsn.replace(f':{user_pass}@', ':****@')
    return dsn


# ======================================================================
# Main
# ======================================================================


async def main():
    print('=' * 60)
    print('  Graphiti MCP Server Pre-flight Check')
    print('  Oracle Linux x86_64 Deployment Verification')
    print('=' * 60)

    load_env_from_file()
    config = TestConfig()
    result = TestResult()

    print(f'\n  Configuration Summary:')
    print(f'    Database DSN:    {_mask_dsn(config.POSTGRES_AGE_DSN)}')
    print(f'    Graph Name:      {config.POSTGRES_AGE_GRAPH_NAME}')
    print(f'    Embedding Dim:   {config.POSTGRES_AGE_EMBEDDING_DIMENSION}')
    print(f'    LLM Base URL:    {config.OPENAI_BASE_URL or "(not set)"}')
    print(f'    LLM Model:       {config.OPENAI_MODEL_NAME}')
    print(f'    Embedding URL:   {config.EMBEDDING_API_URL or "(not set)"}')
    print(f'    Embedding Model: {config.EMBEDDING_MODEL}')

    # Run all tests
    await test_postgres_age(config, result)
    await test_embedding(config, result)
    await test_llm(config, result)

    # Print summary
    success = result.summary()
    if success:
        print('\n  All critical checks PASSED. MCP Server can start.')
    else:
        print('\n  Some checks FAILED. MCP Server should NOT start.')
        print('  Please fix the issues above before proceeding.')

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main())
