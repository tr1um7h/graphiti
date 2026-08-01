"""Semantic attribute constants for Graphiti observability spans.

All span instrumentation code should reference these constants instead of
hardcoding string literals, ensuring naming consistency across the codebase.
"""

# ===== Episode =====
GRAPHITI_EPISODE_NAME = 'graphiti.episode.name'
GRAPHITI_EPISODE_SOURCE = 'graphiti.episode.source'  # "message", "text", "json"
GRAPHITI_EPISODE_SOURCE_DESC = 'graphiti.episode.source_description'

# ===== Search =====
# search() and search_() share the graphiti.search span; type distinguishes mode.
GRAPHITI_SEARCH_TYPE = 'graphiti.search.type'  # "node", "edge", "mmr", "bfs", "hybrid", "semantic"
GRAPHITI_SEARCH_LIMIT = 'graphiti.search.limit'
GRAPHITI_SEARCH_RESULT_COUNT = 'graphiti.search.result_count'
GRAPHITI_SEARCH_DURATION_MS = 'graphiti.search.duration_ms'

# ===== LLM =====
GRAPHITI_LLM_MODEL = 'graphiti.llm.model'
GRAPHITI_LLM_PROVIDER = 'graphiti.llm.provider'  # "openai", "anthropic", "gemini"
GRAPHITI_LLM_TOKENS_IN = 'graphiti.llm.tokens_in'
GRAPHITI_LLM_TOKENS_OUT = 'graphiti.llm.tokens_out'
GRAPHITI_LLM_LATENCY_MS = 'graphiti.llm.latency_ms'
GRAPHITI_LLM_PROMPT_NAME = 'graphiti.llm.prompt_name'  # "extract", "summarize", "dedupe"

# ===== Database =====
GRAPHITI_DB_SYSTEM = 'graphiti.db.system'  # "postgres_age", "neo4j", "falkordb", "kuzu"
GRAPHITI_DB_QUERY_TYPE = 'graphiti.db.query_type'  # "read", "write"
GRAPHITI_DB_ROW_COUNT = 'graphiti.db.row_count'
GRAPHITI_DB_LATENCY_MS = 'graphiti.db.latency_ms'
GRAPHITI_DB_QUERY_TEMPLATE_HASH = 'graphiti.db.query_template_hash'  # low cardinality

# NOTE: raw query text (graphiti.db.query) is DEBUG-only / dev environment.
# Production Collector strips it via attributes processor (see spec §8.2).
# Reasons:
#   1. PII risk - queries embed episode content (user conversations, documents)
#   2. Cardinality explosion - each query is unique

# ===== User / Tenant =====
GRAPHITI_USER_ID = 'graphiti.user.id'  # default "anonymous"; traces/logs only, never in metrics
GRAPHITI_GROUP_ID = 'graphiti.group.id'

# ===== Session =====
GRAPHITI_SESSION_ID = 'graphiti.session.id'
