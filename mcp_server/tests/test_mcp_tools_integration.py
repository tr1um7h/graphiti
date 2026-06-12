#!/usr/bin/env python3
"""
Integration tests for all MCP server tools against a running Docker MCP server.

Prerequisites:
  - Docker services running (postgres-age, embedding-service, mcp-server)
  - MCP server accessible at http://127.0.0.1:8001

Run with:
  cd mcp_server && NO_PROXY='*' uv run pytest tests/test_mcp_tools_integration.py -v -s
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import httpx
import pytest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MCP_URL = os.environ.get('MCP_SERVER_URL', 'http://127.0.0.1:8001/mcp')
MCP_TIMEOUT = float(os.environ.get('MCP_TIMEOUT', '180'))
TEST_GROUP_ID = f'integ_test_{int(time.time())}'

# Max time to wait for async episode processing (LLM calls can be slow)
EPISODE_PROCESSING_TIMEOUT = 180  # seconds
POLL_INTERVAL = 5  # seconds between polls


# ---------------------------------------------------------------------------
# Lightweight JSON-RPC MCP client (avoids MCP SDK proxy issues on macOS)
# ---------------------------------------------------------------------------


class MCPClient:
    """Minimal MCP-over-streamable-HTTP client using httpx."""

    def __init__(self, url: str = MCP_URL, timeout: float = MCP_TIMEOUT):
        self._url = url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._session_id: str | None = None
        self._request_id = 0

    async def connect(self) -> None:
        """Create httpx client and initialize MCP session."""
        self._client = httpx.AsyncClient(proxy=None, timeout=self._timeout)
        await self._initialize()

    async def close(self) -> None:
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def _initialize(self) -> None:
        await self._raw_request('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'integ-test', 'version': '0.1'},
        })
        await self._notify('notifications/initialized', {})

    async def _raw_request(self, method: str, params: dict[str, Any]) -> Any:
        assert self._client is not None
        self._request_id += 1
        body = {
            'jsonrpc': '2.0',
            'id': self._request_id,
            'method': method,
            'params': params,
        }
        headers: dict[str, str] = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
        }
        if self._session_id:
            headers['mcp-session-id'] = self._session_id

        resp = await self._client.post(self._url, json=body, headers=headers)

        sid = resp.headers.get('mcp-session-id')
        if sid:
            self._session_id = sid

        resp.raise_for_status()

        text = resp.text
        for line in text.splitlines():
            if line.startswith('data: '):
                data = json.loads(line[6:])
                if 'result' in data:
                    return data['result']
                if 'error' in data:
                    raise RuntimeError(f'MCP error: {data["error"]}')
        try:
            data = json.loads(text)
            if 'result' in data:
                return data['result']
            if 'error' in data:
                raise RuntimeError(f'MCP error: {data["error"]}')
        except json.JSONDecodeError:
            pass
        return None

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        assert self._client is not None
        body = {'jsonrpc': '2.0', 'method': method, 'params': params}
        headers: dict[str, str] = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
        }
        if self._session_id:
            headers['mcp-session-id'] = self._session_id
        try:
            await self._client.post(self._url, json=body, headers=headers)
        except Exception:
            pass

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._raw_request('tools/list', {})
        return result.get('tools', []) if result else []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP tool and return the parsed response content."""
        result = await self._raw_request('tools/call', {
            'name': name,
            'arguments': arguments,
        })
        if result is None:
            return {}
        content = result.get('content', [])
        if content and content[0].get('type') == 'text':
            text = content[0]['text']
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {'_raw': text}
        return result

    async def poll_episodes(
        self,
        group_id: str,
        min_count: int = 1,
        timeout: float = EPISODE_PROCESSING_TIMEOUT,
    ) -> list[dict[str, Any]]:
        """Poll get_episodes until at least min_count episodes appear or timeout."""
        deadline = time.time() + timeout
        last_count = 0
        while time.time() < deadline:
            result = await self.call_tool('get_episodes', {
                'group_ids': [group_id],
                'max_episodes': 50,
            })
            episodes = result.get('episodes', [])
            last_count = len(episodes)
            if last_count >= min_count:
                return episodes
            remaining = int(deadline - time.time())
            logger.info(
                f'Polling episodes: found {last_count}/{min_count}, '
                f'{remaining}s remaining...'
            )
            await asyncio.sleep(POLL_INTERVAL)
        logger.warning(f'Polling timed out with {last_count} episodes (wanted {min_count})')
        return []

    async def poll_facts(
        self,
        query: str,
        group_id: str,
        min_count: int = 1,
        timeout: float = EPISODE_PROCESSING_TIMEOUT,
    ) -> list[dict[str, Any]]:
        """Poll search_memory_facts until at least min_count facts appear or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = await self.call_tool('search_memory_facts', {
                'query': query,
                'group_ids': [group_id],
                'max_facts': 20,
            })
            facts = result.get('facts', [])
            if len(facts) >= min_count:
                return facts
            remaining = int(deadline - time.time())
            logger.info(
                f'Polling facts: found {len(facts)}/{min_count}, '
                f'{remaining}s remaining...'
            )
            await asyncio.sleep(POLL_INTERVAL)
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def group_id() -> str:
    return TEST_GROUP_ID


@pytest.fixture
async def mcp() -> MCPClient:
    """Per-test MCP client with its own session."""
    client = MCPClient()
    await client.connect()
    try:
        yield client
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Tests — ordered by class name: connectivity → add → wait → read → delete → clear
# ---------------------------------------------------------------------------


class Test00Connectivity:
    """Verify MCP server connectivity and tool discovery."""

    async def test_server_reachable(self, mcp: MCPClient) -> None:
        tools = await mcp.list_tools()
        assert len(tools) > 0, 'No tools returned from MCP server'
        tool_names = [t['name'] for t in tools]
        logger.info(f'Available tools: {tool_names}')

    async def test_expected_tools_present(self, mcp: MCPClient) -> None:
        tools = await mcp.list_tools()
        tool_names = {t['name'] for t in tools}
        expected = {
            'add_memory',
            'search_nodes',
            'search_memory_facts',
            'get_episodes',
            'get_entity_edge',
            'delete_entity_edge',
            'delete_episode',
            'clear_graph',
            'get_status',
        }
        missing = expected - tool_names
        assert not missing, f'Missing tools: {missing}'

    async def test_tool_schemas_have_descriptions(self, mcp: MCPClient) -> None:
        """Verify each tool has a description and input schema."""
        tools = await mcp.list_tools()
        for tool in tools:
            assert 'name' in tool, f'Tool missing name: {tool}'
            assert 'description' in tool, f'Tool {tool["name"]} missing description'
            assert 'inputSchema' in tool, f'Tool {tool["name"]} missing inputSchema'
            logger.info(f'Tool {tool["name"]}: {tool["description"][:60]}...')


class Test01GetStatus:
    """Test get_status tool."""

    async def test_get_status_ok(self, mcp: MCPClient) -> None:
        result = await mcp.call_tool('get_status', {})
        logger.info(f'get_status result: {result}')
        assert 'error' not in result or result.get('error') is None, (
            f'get_status returned error: {result.get("error")}'
        )
        status = result.get('status', '')
        assert status == 'ok', f'Expected status=ok, got: {status}'
        message = result.get('message', '')
        assert 'database' in message.lower() or 'running' in message.lower(), (
            f'Status message unexpected: {message}'
        )


class Test02AddMemory:
    """Test add_memory tool — adds episodes for subsequent tests."""

    async def test_add_text_episode(self, mcp: MCPClient, group_id: str) -> None:
        result = await mcp.call_tool('add_memory', {
            'name': 'Integration Test - Graphiti Overview',
            'episode_body': (
                'Graphiti is a knowledge graph framework built by Zep. '
                'It provides temporal knowledge graphs for AI agents. '
                'The founder of Zep is Daniel Chalef. '
                'Graphiti supports Neo4j, FalkorDB, and PostgreSQL with AGE as graph databases.'
            ),
            'group_id': group_id,
            'source': 'text',
            'source_description': 'integration test - text episode',
        })
        logger.info(f'add_memory text result: {result}')
        assert 'error' not in result or result.get('error') is None, (
            f'add_memory returned error: {result}'
        )
        msg = result.get('message', '')
        assert 'queued' in msg.lower(), f'Expected queued message, got: {msg}'

    async def test_add_message_episode(self, mcp: MCPClient, group_id: str) -> None:
        result = await mcp.call_tool('add_memory', {
            'name': 'Integration Test - Conversation',
            'episode_body': (
                'User: What databases does Graphiti support?\n'
                'Assistant: Graphiti supports three graph database backends: '
                'Neo4j (the original), FalkorDB (a Redis-based graph), '
                'and PostgreSQL with Apache AGE extension. '
                'PostgreSQL AGE is recommended for production deployments.'
            ),
            'group_id': group_id,
            'source': 'message',
            'source_description': 'integration test - conversation',
        })
        logger.info(f'add_memory message result: {result}')
        assert 'error' not in result or result.get('error') is None

    async def test_add_json_episode(self, mcp: MCPClient, group_id: str) -> None:
        json_data = json.dumps({
            'project': 'Graphiti',
            'version': '0.29',
            'features': ['knowledge graph', 'entity extraction', 'temporal awareness'],
            'team': {'lead': 'Zep', 'contributors': 50},
        })
        result = await mcp.call_tool('add_memory', {
            'name': 'Integration Test - Project Info',
            'episode_body': json_data,
            'group_id': group_id,
            'source': 'json',
            'source_description': 'integration test - JSON data',
        })
        logger.info(f'add_memory json result: {result}')
        assert 'error' not in result or result.get('error') is None

    async def test_add_memory_returns_immediately(self, mcp: MCPClient, group_id: str) -> None:
        """Verify add_memory returns quickly (async queueing, not blocking)."""
        start = time.time()
        result = await mcp.call_tool('add_memory', {
            'name': 'Integration Test - Speed Check',
            'episode_body': 'This episode tests that add_memory returns quickly via queue.',
            'group_id': group_id,
            'source': 'text',
        })
        elapsed = time.time() - start
        logger.info(f'add_memory returned in {elapsed:.1f}s')
        assert 'error' not in result or result.get('error') is None
        # Should return within a few seconds (just queuing), not wait for LLM processing
        assert elapsed < 30, f'add_memory took {elapsed:.1f}s — should return quickly'


class Test03WaitForProcessing:
    """Wait for async episode processing to complete using polling."""

    async def test_poll_until_episodes_appear(self, mcp: MCPClient, group_id: str) -> None:
        """Poll for episodes instead of fixed sleep — handles slow LLM gracefully."""
        logger.info(
            f'Polling for episodes (timeout={EPISODE_PROCESSING_TIMEOUT}s)...'
        )
        episodes = await mcp.poll_episodes(group_id, min_count=1)
        logger.info(f'Found {len(episodes)} episodes after polling')
        assert len(episodes) >= 1, (
            f'Expected at least 1 episode but found {len(episodes)} after '
            f'{EPISODE_PROCESSING_TIMEOUT}s. Episode processing may have failed.'
        )


class Test04GetEpisodes:
    """Test get_episodes tool."""

    async def test_get_episodes_with_group(self, mcp: MCPClient, group_id: str) -> None:
        episodes = await mcp.poll_episodes(group_id, min_count=1)
        assert len(episodes) >= 1, f'Expected episodes but got none'
        ep = episodes[0]
        assert 'uuid' in ep, f'Episode missing uuid: {ep}'
        assert 'name' in ep, f'Episode missing name: {ep}'
        assert 'content' in ep, f'Episode missing content: {ep}'
        assert 'group_id' in ep, f'Episode missing group_id: {ep}'
        assert ep['group_id'] == group_id, (
            f'Episode group_id mismatch: expected {group_id}, got {ep["group_id"]}'
        )
        logger.info(f'First episode: name={ep.get("name")}, uuid={ep.get("uuid")}')

    async def test_get_episodes_empty_group(self, mcp: MCPClient) -> None:
        result = await mcp.call_tool('get_episodes', {
            'group_ids': ['nonexistent_group_xyz_12345'],
            'max_episodes': 10,
        })
        episodes = result.get('episodes', [])
        assert len(episodes) == 0, f'Expected no episodes for nonexistent group, got: {result}'
        assert result.get('message') is not None

    async def test_get_episodes_max_limit(self, mcp: MCPClient, group_id: str) -> None:
        """Verify max_episodes limits results."""
        result = await mcp.call_tool('get_episodes', {
            'group_ids': [group_id],
            'max_episodes': 1,
        })
        episodes = result.get('episodes', [])
        assert len(episodes) <= 1, f'Expected at most 1 episode, got {len(episodes)}'

    async def test_get_episodes_field_structure(self, mcp: MCPClient, group_id: str) -> None:
        """Verify episode fields match expected schema."""
        episodes = await mcp.poll_episodes(group_id, min_count=1)
        if not episodes:
            pytest.skip('No episodes available')
        ep = episodes[0]
        expected_fields = {'uuid', 'name', 'content', 'created_at', 'source', 'group_id'}
        actual_fields = set(ep.keys())
        missing = expected_fields - actual_fields
        assert not missing, f'Episode missing fields: {missing}'
        # source should be one of the known types
        assert ep['source'] in ('text', 'json', 'message', 'twitter', 'email'), (
            f'Unexpected source type: {ep["source"]}'
        )


class Test05SearchNodes:
    """Test search_nodes tool."""

    async def test_search_nodes_basic(self, mcp: MCPClient, group_id: str) -> None:
        # Wait for data to be processed first
        episodes = await mcp.poll_episodes(group_id, min_count=1)
        if not episodes:
            pytest.skip('No episodes processed — cannot test search')

        result = await mcp.call_tool('search_nodes', {
            'query': 'Graphiti knowledge graph',
            'group_ids': [group_id],
            'max_nodes': 10,
        })
        nodes = result.get('nodes', [])
        logger.info(f'search_nodes returned {len(nodes)} nodes')
        assert result.get('message') is not None
        if nodes:
            node = nodes[0]
            assert 'uuid' in node, f'Node missing uuid: {node}'
            assert 'name' in node, f'Node missing name: {node}'

    async def test_search_nodes_no_results(self, mcp: MCPClient, group_id: str) -> None:
        result = await mcp.call_tool('search_nodes', {
            'query': 'xyznonexistentterm123abc',
            'group_ids': [group_id],
            'max_nodes': 5,
        })
        nodes = result.get('nodes', [])
        logger.info(f'search_nodes no-match returned {len(nodes)} nodes')
        # Should return empty or very few results
        assert len(nodes) == 0, f'Expected 0 nodes for gibberish query, got {len(nodes)}'

    async def test_search_nodes_max_nodes_respected(self, mcp: MCPClient, group_id: str) -> None:
        result = await mcp.call_tool('search_nodes', {
            'query': 'Graphiti',
            'group_ids': [group_id],
            'max_nodes': 2,
        })
        nodes = result.get('nodes', [])
        assert len(nodes) <= 2, f'Expected at most 2 nodes, got {len(nodes)}'


class Test06SearchMemoryFacts:
    """Test search_memory_facts tool."""

    async def test_search_facts_basic(self, mcp: MCPClient, group_id: str) -> None:
        # Wait for episodes to be processed
        episodes = await mcp.poll_episodes(group_id, min_count=1)
        if not episodes:
            pytest.skip('No episodes processed — cannot test fact search')

        # Poll for facts — LLM may or may not extract relationships
        facts = await mcp.poll_facts(
            query='database support PostgreSQL',
            group_id=group_id,
            min_count=1,
            timeout=60,
        )
        logger.info(f'search_memory_facts returned {len(facts)} facts')
        if facts:
            fact = facts[0]
            assert 'uuid' in fact, f'Fact missing uuid: {fact}'
            # Verify fact has either name, fact, or source/target
            has_content = any(k in fact for k in ('name', 'fact', 'source', 'target'))
            assert has_content, f'Fact missing content fields: {fact}'
        else:
            logger.warning('No facts extracted — LLM may not have found relationships')

    async def test_search_facts_max_facts_respected(self, mcp: MCPClient, group_id: str) -> None:
        result = await mcp.call_tool('search_memory_facts', {
            'query': 'Graphiti',
            'group_ids': [group_id],
            'max_facts': 2,
        })
        facts = result.get('facts', [])
        assert len(facts) <= 2, f'Expected at most 2 facts, got {len(facts)}'

    async def test_search_facts_invalid_max(self, mcp: MCPClient, group_id: str) -> None:
        """max_facts <= 0 should return an error."""
        result = await mcp.call_tool('search_memory_facts', {
            'query': 'test',
            'group_ids': [group_id],
            'max_facts': 0,
        })
        has_error = result.get('error') is not None
        assert has_error, f'Expected error for max_facts=0, got: {result}'


class Test07GetEntityEdge:
    """Test get_entity_edge tool."""

    async def test_get_entity_edge_not_found(self, mcp: MCPClient) -> None:
        result = await mcp.call_tool('get_entity_edge', {
            'uuid': 'nonexistent-uuid-12345',
        })
        has_error = (
            result.get('error') is not None
            or 'not found' in str(result).lower()
        )
        logger.info(f'get_entity_edge not found result: {result}')
        assert has_error, f'Expected error for nonexistent edge, got: {result}'

    async def test_get_entity_edge_by_search(self, mcp: MCPClient, group_id: str) -> None:
        # Wait for facts
        facts = await mcp.poll_facts('Graphiti', group_id, min_count=1, timeout=60)
        if not facts:
            pytest.skip('No facts found — LLM may not have extracted relationships')

        edge_uuid = facts[0].get('uuid')
        if not edge_uuid:
            pytest.skip('Fact has no UUID field')

        result = await mcp.call_tool('get_entity_edge', {'uuid': edge_uuid})
        logger.info(f'get_entity_edge result: {result}')
        assert 'error' not in result or result.get('error') is None, (
            f'get_entity_edge failed: {result}'
        )
        assert result.get('uuid') == edge_uuid, (
            f'UUID mismatch: expected {edge_uuid}, got {result.get("uuid")}'
        )


class Test08DeleteEntityEdge:
    """Test delete_entity_edge tool."""

    async def test_delete_nonexistent_edge(self, mcp: MCPClient) -> None:
        result = await mcp.call_tool('delete_entity_edge', {
            'uuid': 'nonexistent-uuid-99999',
        })
        logger.info(f'delete_entity_edge nonexistent result: {result}')
        has_error = (
            result.get('error') is not None
            or 'not found' in str(result).lower()
        )
        assert has_error, f'Expected error for nonexistent edge, got: {result}'

    async def test_delete_real_entity_edge(self, mcp: MCPClient, group_id: str) -> None:
        """Find a real edge via search, delete it, verify deletion."""
        facts = await mcp.poll_facts('Graphiti', group_id, min_count=1, timeout=60)
        if not facts:
            pytest.skip('No facts available to delete')

        edge_uuid = facts[0].get('uuid')
        if not edge_uuid:
            pytest.skip('Fact has no UUID')

        # Delete the edge
        result = await mcp.call_tool('delete_entity_edge', {'uuid': edge_uuid})
        logger.info(f'delete_entity_edge result: {result}')
        assert 'error' not in result or result.get('error') is None, (
            f'delete_entity_edge failed: {result}'
        )

        # Verify it's gone
        get_result = await mcp.call_tool('get_entity_edge', {'uuid': edge_uuid})
        has_error = (
            get_result.get('error') is not None
            or 'not found' in str(get_result).lower()
        )
        assert has_error, f'Edge still exists after deletion: {get_result}'


class Test09DeleteEpisode:
    """Test delete_episode tool."""

    async def test_delete_nonexistent_episode(self, mcp: MCPClient) -> None:
        result = await mcp.call_tool('delete_episode', {
            'uuid': 'nonexistent-episode-99999',
        })
        logger.info(f'delete_episode nonexistent result: {result}')
        has_error = (
            result.get('error') is not None
            or 'not found' in str(result).lower()
        )
        assert has_error, f'Expected error for nonexistent episode, got: {result}'

    async def test_delete_real_episode(self, mcp: MCPClient, group_id: str) -> None:
        episodes = await mcp.poll_episodes(group_id, min_count=1)
        if not episodes:
            pytest.skip('No episodes to delete')

        ep_uuid = episodes[0].get('uuid')
        if not ep_uuid:
            pytest.skip('Episode has no UUID')

        # Delete the episode
        result = await mcp.call_tool('delete_episode', {'uuid': ep_uuid})
        logger.info(f'delete_episode result: {result}')
        assert 'error' not in result or result.get('error') is None, (
            f'delete_episode failed: {result}'
        )
        msg = result.get('message', '')
        assert msg, 'delete_episode returned empty response'

        # Verify it's gone — get_episodes should not return it
        await asyncio.sleep(2)
        ep_result = await mcp.call_tool('get_episodes', {
            'group_ids': [group_id],
            'max_episodes': 50,
        })
        remaining_uuids = [e['uuid'] for e in ep_result.get('episodes', [])]
        assert ep_uuid not in remaining_uuids, (
            f'Episode {ep_uuid} still exists after deletion'
        )


class Test10ClearGraph:
    """Test clear_graph tool — cleans up all test data."""

    async def test_clear_graph_test_group(self, mcp: MCPClient, group_id: str) -> None:
        result = await mcp.call_tool('clear_graph', {
            'group_ids': [group_id],
        })
        logger.info(f'clear_graph result: {result}')
        assert 'error' not in result or result.get('error') is None, (
            f'clear_graph failed: {result}'
        )
        msg = result.get('message', '')
        assert group_id in msg, f'Expected group_id in message, got: {msg}'

    async def test_verify_data_cleared(self, mcp: MCPClient, group_id: str) -> None:
        """Verify that data was actually cleared."""
        await asyncio.sleep(3)

        result = await mcp.call_tool('get_episodes', {
            'group_ids': [group_id],
            'max_episodes': 10,
        })
        episodes = result.get('episodes', [])
        assert len(episodes) == 0, (
            f'Expected 0 episodes after clear, but found {len(episodes)}: {episodes}'
        )

    async def test_clear_graph_empty_group(self, mcp: MCPClient) -> None:
        """Clearing a nonexistent group should succeed (no-op)."""
        result = await mcp.call_tool('clear_graph', {
            'group_ids': ['nonexistent_group_to_clear'],
        })
        logger.info(f'clear_graph empty group result: {result}')
        assert 'error' not in result or result.get('error') is None


class Test11ClearGraphRaceCondition:
    """Test the race condition fix: clear_graph should drain queues first."""

    async def test_clear_after_queued_episodes(
        self, mcp: MCPClient, group_id: str
    ) -> None:
        """Add episodes then immediately clear — verifies queue draining."""
        race_group = f'{group_id}_race'

        # Add multiple episodes (they go into the queue)
        for i in range(3):
            result = await mcp.call_tool('add_memory', {
                'name': f'Race Test Episode {i}',
                'episode_body': (
                    f'This is race test episode number {i}. '
                    f'It contains unique content for testing race conditions in '
                    f'the knowledge graph system.'
                ),
                'group_id': race_group,
                'source': 'text',
                'source_description': 'race condition test',
            })
            assert 'error' not in result or result.get('error') is None

        # Immediately clear — should wait for queue to drain first
        clear_result = await mcp.call_tool('clear_graph', {
            'group_ids': [race_group],
        })
        logger.info(f'clear_graph after queued episodes: {clear_result}')
        assert 'error' not in clear_result or clear_result.get('error') is None, (
            f'clear_graph failed: {clear_result}'
        )

        # Wait then verify data is truly cleared
        await asyncio.sleep(5)

        verify = await mcp.call_tool('get_episodes', {
            'group_ids': [race_group],
            'max_episodes': 10,
        })
        episodes = verify.get('episodes', [])
        assert len(episodes) == 0, (
            f'Race condition detected: {len(episodes)} episodes remain after clear. '
            f'The queue drain fix may not be working.'
        )
