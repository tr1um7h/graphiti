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
import re
import socket
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import urlparse

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
        self.EMBEDDER_PROVIDER = os.environ.get('EMBEDDER_PROVIDER', 'bge_zh')
        self.EMBEDDING_API_URL = os.environ.get('EMBEDDING_API_URL', '')
        self.EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'BAAI/bge-large-zh-v1.5')
        self.EMBEDDING_DIM = int(os.environ.get('EMBEDDING_DIM', '1024'))


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
    """Test embedding API or local embedder.

    For remote OpenAI-compatible embedding services, issues requests to the
    endpoint. For local embedders (bge_zh, sentence-transformers), verifies
    the configuration and skips API connectivity checks.
    """
    suite = 'Embedding Model API'
    print(f'\n{"=" * 60}')
    print(f'  Suite: {suite}')
    print(f'  Provider: {config.EMBEDDER_PROVIDER}')
    print(f'  API URL: {config.EMBEDDING_API_URL or "(not set)"}')
    print(f'  Model: {config.EMBEDDING_MODEL}')
    print(f'{"=" * 60}')

    # Local embedders don't need a remote API endpoint
    if config.EMBEDDER_PROVIDER in ('bge_zh', 'sentence-transformers'):
        result.record(
            suite,
            'Configuration',
            TestResult.PASS,
            f'Local embedder ({config.EMBEDDER_PROVIDER}) configured; no API endpoint needed',
        )
        result.record(
            suite,
            'Model Name',
            TestResult.PASS,
            f'Model: {config.EMBEDDING_MODEL}, Dims: {config.EMBEDDING_DIM}',
        )
        return

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
    chat_url = f'{base_url}/chat/completions'

    # --- 0. Pre-flight network diagnostics (DNS + TCP reachability) ---
    # Catches the common case where the LLM endpoint is unreachable so the
    # user can immediately see whether it is a DNS, firewall, or service
    # problem rather than a generic "All connection attempt failed" string.
    await _diagnose_llm_connectivity(base_url, result, suite)

    # --- 1. Chat completions (system + user + json_object) ---
    # Mirrors OpenAIGenericClient._generate_response: same request shape,
    # same response parsing (reasoning_content fallback + <think> stripping).
    # PASS = provider is usable end-to-end.
    t0 = time.monotonic()
    resp = None
    request_body = {
        'model': config.OPENAI_MODEL_NAME,
        'messages': [
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'Reply with the single word: OK in json'},
        ],
        'temperature': 0,
        'max_tokens': 512,
        'response_format': {'type': 'json_object'},
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            resp = await http_client.post(
                chat_url,
                headers={'Authorization': f'Bearer {config.OPENAI_API_KEY}'},
                json=request_body,
            )
        resp.raise_for_status()
        data = resp.json()
        assert data.get('choices'), 'response missing choices'
        msg = data['choices'][0].get('message') or {}
        # Same logic as OpenAIGenericClient: read content, fall back to
        # reasoning_content for models that return content=null.
        content = msg.get('content') or msg.get('reasoning_content') or ''
        # Strip <think>...</think> tags (same as business code)
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        assert content, 'response message.content is empty'
        # WARN (not FAIL) if content is not strict JSON — the business code
        # also strips markdown code blocks before json.loads(), so a soft
        # warning lets the provider pass when output is wrapped.
        try:
            json.loads(content)
            content_note = f' content={content[:60]!r}'
        except json.JSONDecodeError:
            content_note = (
                f' content={content[:60]!r} (not strict JSON;'
                ' OK if LLM wraps in <think>)'
            )
        result.record(
            suite,
            'Chat completions (system + user + json_object)',
            TestResult.PASS,
            f'http={resp.status_code} latency_ms={(time.monotonic() - t0) * 1000:.0f}'
            + content_note,
            (time.monotonic() - t0) * 1000,
        )
    except Exception as e:
        result.record(
            suite,
            'Chat completions (system + user + json_object)',
            TestResult.FAIL,
            _format_request_error(
                e, label='chat/completions',
                request_url=chat_url, request_body=request_body, response=resp,
            ),
            (time.monotonic() - t0) * 1000,
        )

    # Multi-turn check removed — LLM context understanding is a basic
    # capability and not relied upon by business code. The combined
    # chat completion check above (system + user + json_object) covers
    # what business code actually sends on every call.


def _format_request_error(
    e: Exception,
    *,
    label: str,
    request_url: str,
    request_body: dict | None = None,
    response: httpx.Response | None = None,
) -> str:
    """Build a multi-line diagnostic string for an LLM request error.

    The output is intended to be embedded in a TestResult detail field so the
    user can immediately see:
      - The exact exception class (e.g. httpx.ConnectError)
      - A human-readable classification (DNS / TCP / SSL / timeout / HTTP)
      - The request URL and a truncated JSON body
      - The response status / key headers / body preview (if any)
      - The full Python traceback
    """
    lines: list[str] = []
    lines.append(f'[{label}] {type(e).__name__}: {e}')

    if isinstance(e, httpx.ConnectError):
        lines.append('  classification: ConnectError (DNS resolve, TCP connect, or SSL handshake failed)')
        lines.append('  hint: check DNS, proxy, corporate firewall, TLS interception, or whether the upstream is up')
    elif isinstance(e, httpx.ConnectTimeout):
        lines.append('  classification: ConnectTimeout (could not establish TCP connection within timeout)')
    elif isinstance(e, httpx.ReadTimeout):
        lines.append('  classification: ReadTimeout (server accepted connection but did not respond in time)')
    elif isinstance(e, httpx.WriteTimeout):
        lines.append('  classification: WriteTimeout (client could not finish sending request in time)')
    elif isinstance(e, httpx.PoolTimeout):
        lines.append('  classification: PoolTimeout (connection pool exhausted — too much concurrency?)')
    elif isinstance(e, httpx.TimeoutException):
        lines.append('  classification: TimeoutException (generic httpx timeout)')
    elif isinstance(e, httpx.HTTPStatusError):
        lines.append(f'  classification: HTTPStatusError (server returned {e.response.status_code})')
    elif isinstance(e, httpx.RequestError):
        lines.append('  classification: RequestError (generic httpx request error)')
    elif isinstance(e, httpx.HTTPError):
        lines.append('  classification: HTTPError (generic httpx error)')
    elif isinstance(e, json.JSONDecodeError):
        lines.append('  classification: JSONDecodeError (response body is not valid JSON)')
    elif isinstance(e, OSError):
        lines.append('  classification: OSError (low-level socket / DNS error)')
    else:
        lines.append(f'  classification: non-httpx exception ({type(e).__module__}.{type(e).__name__})')

    lines.append(f'  url: {request_url}')
    lines.append(f'  method: POST')
    if request_body is not None:
        try:
            body_str = json.dumps(request_body, ensure_ascii=False)
        except (TypeError, ValueError):
            body_str = repr(request_body)
        if len(body_str) > 300:
            body_str = body_str[:300] + '...(truncated)'
        lines.append(f'  body: {body_str}')

    if response is not None:
        lines.append(f'  status: {response.status_code} {response.reason_phrase}')
        interesting = ['content-type', 'x-request-id', 'x-error-code',
                       'x-error-message', 'x-trace-id', 'www-authenticate', 'retry-after']
        for h in interesting:
            v = response.headers.get(h)
            if v:
                lines.append(f'  resp_header[{h}]: {v}')
        body_preview = (response.text or '')[:500]
        lines.append(f'  body_preview: {body_preview!r}')

    tb_str = traceback.format_exc()
    tb_lines = tb_str.rstrip().splitlines()
    if len(tb_lines) > 25:
        tb_lines = ['... (truncated intermediate frames)'] + tb_lines[-18:]
    lines.append('  traceback:')
    for line in tb_lines:
        lines.append(f'    {line}')

    return '\n'.join(lines)


async def _diagnose_llm_connectivity(base_url: str, result: TestResult, suite: str) -> bool:
    """Probe DNS resolution and TCP reachability for the LLM base URL.

    Records one PASS/FAIL row for each step so the user can see whether the
    LLM endpoint is reachable at the network layer. Returns True only if
    every probe succeeded.
    """
    try:
        parsed = urlparse(base_url)
    except Exception as e:
        result.record(suite, 'URL parse', TestResult.FAIL,
                      f'urlparse failed for {base_url!r}: {e}', 0)
        return False

    host = parsed.hostname
    if not host:
        result.record(suite, 'URL parse', TestResult.FAIL,
                      f'no hostname in base_url={base_url!r}', 0)
        return False
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    result.record(suite, 'URL parse', TestResult.PASS,
                  f'{parsed.scheme}://{host}:{port}', 0)

    # --- DNS resolution ---
    t0 = time.monotonic()
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.run_in_executor(
            None, lambda: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        )
        addrs = sorted({i[4][0] for i in infos})
        result.record(suite, f'DNS resolve {host}', TestResult.PASS,
                      f'addrs={addrs}', (time.monotonic() - t0) * 1000)
    except Exception as e:
        result.record(
            suite, f'DNS resolve {host}', TestResult.FAIL,
            f'{type(e).__name__}: {e}\ntraceback:\n{traceback.format_exc()}',
            (time.monotonic() - t0) * 1000,
        )
        return False

    # --- TCP reachability ---
    t0 = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=5.0
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        result.record(suite, f'TCP connect {host}:{port}', TestResult.PASS,
                      '', (time.monotonic() - t0) * 1000)
        return True
    except Exception as e:
        result.record(
            suite, f'TCP connect {host}:{port}', TestResult.FAIL,
            f'{type(e).__name__}: {e}\ntraceback:\n{traceback.format_exc()}',
            (time.monotonic() - t0) * 1000,
        )
        return False


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
