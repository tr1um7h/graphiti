"""Tests for Data API router."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# Mock the ZepGraphiti before importing the app
@pytest.fixture
def mock_graphiti():
    """Create a mock Graphiti instance."""
    graphiti = MagicMock()
    driver = MagicMock()
    driver.schema = 'test_schema'
    driver.execute_query = AsyncMock(return_value=([], None, []))
    graphiti.driver = driver
    return graphiti


@pytest.fixture
def client(mock_graphiti):
    """Create a test client with mocked dependencies."""
    # Import after mocking
    from fastapi import FastAPI
    from graph_service.routers import data

    app = FastAPI()
    app.include_router(data.router, prefix='/rest')

    # Override the dependency
    async def override_graphiti():
        return mock_graphiti

    from graph_service.zep_graphiti import get_graphiti
    app.dependency_overrides[get_graphiti] = override_graphiti

    return TestClient(app)


class TestGetGroups:
    async def test_get_groups_empty(self, client, mock_graphiti):
        """Test getting groups when none exist."""
        mock_graphiti.driver.execute_query.return_value = ([], None, [])

        response = client.get('/rest/data/groups')
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_groups_with_data(self, client, mock_graphiti):
        """Test getting groups with data."""
        # Mock responses for each table query
        def execute_query_side_effect(query, params=None):
            if 'entity_nodes' in query:
                return ([{'group_id': 'group_a', 'count': 10}], None, [])
            return ([], None, [])

        mock_graphiti.driver.execute_query.side_effect = execute_query_side_effect

        response = client.get('/rest/data/groups')
        assert response.status_code == 200
        result = response.json()
        assert len(result) >= 1
        assert result[0]['group_id'] == 'group_a'


class TestPatchValidation:
    async def test_preview_patch_invalid_json(self, client, mock_graphiti):
        """Test preview with invalid JSON file."""
        # Create a fake JSON file
        file_content = b'not valid json'

        response = client.post(
            '/rest/data/patch/preview',
            files={'file': ('patch.json', file_content, 'application/json')}
        )
        assert response.status_code == 400
        assert 'Invalid JSON' in response.json()['detail']

    async def test_preview_patch_missing_version(self, client, mock_graphiti):
        """Test preview with patch missing version field."""
        patch = {
            'metadata': {'from_group_id': 'a'},
            'changes': {}
        }
        file_content = json.dumps(patch).encode()

        response = client.post(
            '/rest/data/patch/preview',
            files={'file': ('patch.json', file_content, 'application/json')}
        )
        assert response.status_code == 400
        assert 'version' in response.json()['detail']

    async def test_preview_patch_missing_metadata(self, client, mock_graphiti):
        """Test preview with patch missing metadata field."""
        patch = {
            'version': 1,
            'changes': {}
        }
        file_content = json.dumps(patch).encode()

        response = client.post(
            '/rest/data/patch/preview',
            files={'file': ('patch.json', file_content, 'application/json')}
        )
        assert response.status_code == 400
        assert 'metadata' in response.json()['detail']

    async def test_preview_patch_missing_changes(self, client, mock_graphiti):
        """Test preview with patch missing changes field."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'a'}
        }
        file_content = json.dumps(patch).encode()

        response = client.post(
            '/rest/data/patch/preview',
            files={'file': ('patch.json', file_content, 'application/json')}
        )
        assert response.status_code == 400
        assert 'changes' in response.json()['detail']

    async def test_preview_patch_valid(self, client, mock_graphiti):
        """Test preview with valid patch."""
        patch = {
            'version': 1,
            'metadata': {
                'from_group_id': 'group_a',
                'to_group_id': 'group_b',
                'created_at': '2024-01-01T00:00:00Z'
            },
            'changes': {
                'entity_nodes': {
                    'added': [{'name': 'Alice'}],
                    'removed': [],
                    'modified': [],
                    'conflicts': []
                }
            }
        }
        file_content = json.dumps(patch).encode()

        response = client.post(
            '/rest/data/patch/preview',
            files={'file': ('patch.json', file_content, 'application/json')}
        )
        assert response.status_code == 200
        result = response.json()
        assert result['version'] == 1
        assert 'summary' in result
        assert 'entity_nodes' in result['summary']
        assert result['summary']['entity_nodes']['added'] == 1
        # Should NOT include full patch content
        assert 'patch' not in result or 'changes' not in result.get('patch', {})


class TestApplyPatch:
    async def test_apply_patch_invalid_strategy(self, client, mock_graphiti):
        """Test apply with invalid strategy."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'a'},
            'changes': {}
        }

        response = client.post(
            '/rest/data/patch/apply',
            json={
                'patch': patch,
                'to_group_id': 'b',
                'strategy': 'invalid'
            }
        )
        assert response.status_code == 400
        assert 'Invalid strategy' in response.json()['detail']

    async def test_apply_patch_missing_to_group(self, client, mock_graphiti):
        """Test apply without to_group_id."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'a'},
            'changes': {}
        }

        response = client.post(
            '/rest/data/patch/apply',
            json={'patch': patch}  # missing to_group_id
        )
        assert response.status_code == 422  # Validation error
