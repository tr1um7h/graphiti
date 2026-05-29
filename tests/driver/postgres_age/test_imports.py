import importlib
import sys
import types

from graphiti_core.driver.driver import GraphProvider
from graphiti_core.driver.postgres_age.deps import import_postgres_age_dependencies


def test_postgres_age_provider_exists():
    assert GraphProvider.POSTGRES_AGE.value == 'postgres_age'


def test_postgres_age_public_export():
    module = importlib.import_module('graphiti_core.driver.postgres_age')
    assert hasattr(module, 'PostgresAgeDriver')


def test_import_postgres_age_dependencies_returns_named_dependencies(monkeypatch):
    register_vector_async = object()
    async_connection = type('AsyncConnection', (), {})
    async_cursor = type('AsyncCursor', (), {})
    async_connection_pool = type('AsyncConnectionPool', (), {})
    jsonb = type('Jsonb', (), {})
    dict_row = object()
    sql = object()

    pgvector_module = types.ModuleType('pgvector')
    pgvector_psycopg_module = types.ModuleType('pgvector.psycopg')
    pgvector_psycopg_module.register_vector_async = register_vector_async

    psycopg_module = types.ModuleType('psycopg')
    psycopg_module.AsyncConnection = async_connection
    psycopg_module.AsyncCursor = async_cursor
    psycopg_module.sql = sql

    psycopg_rows_module = types.ModuleType('psycopg.rows')
    psycopg_rows_module.dict_row = dict_row

    psycopg_types_module = types.ModuleType('psycopg.types')
    psycopg_types_json_module = types.ModuleType('psycopg.types.json')
    psycopg_types_json_module.Jsonb = jsonb

    psycopg_pool_module = types.ModuleType('psycopg_pool')
    psycopg_pool_module.AsyncConnectionPool = async_connection_pool

    monkeypatch.setitem(sys.modules, 'pgvector', pgvector_module)
    monkeypatch.setitem(sys.modules, 'pgvector.psycopg', pgvector_psycopg_module)
    monkeypatch.setitem(sys.modules, 'psycopg', psycopg_module)
    monkeypatch.setitem(sys.modules, 'psycopg.rows', psycopg_rows_module)
    monkeypatch.setitem(sys.modules, 'psycopg.types', psycopg_types_module)
    monkeypatch.setitem(sys.modules, 'psycopg.types.json', psycopg_types_json_module)
    monkeypatch.setitem(sys.modules, 'psycopg_pool', psycopg_pool_module)

    dependencies = import_postgres_age_dependencies()

    assert dependencies.register_vector_async is register_vector_async
    assert dependencies.AsyncConnection is async_connection
    assert dependencies.AsyncCursor is async_cursor
    assert dependencies.AsyncConnectionPool is async_connection_pool
    assert dependencies.Jsonb is jsonb
    assert dependencies.dict_row is dict_row
    assert dependencies.sql is sql


def test_import_postgres_age_dependencies_raises_helpful_import_error(monkeypatch):
    original_import = __import__

    def fail_pgvector_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'pgvector.psycopg':
            raise ImportError('missing pgvector')
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr('builtins.__import__', fail_pgvector_import)

    try:
        import_postgres_age_dependencies()
    except ImportError as exc:
        assert 'PostgresAgeDriver requires graphiti-core[postgres-age]' in str(exc)
        assert 'pip install graphiti-core[postgres-age]' in str(exc)
        assert 'uv sync --extra postgres-age' in str(exc)
    else:
        raise AssertionError('Expected ImportError')
