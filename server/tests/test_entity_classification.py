"""Unit tests for entity classification feature.

Tests cover:
- DEFAULT_ENTITY_TYPES structure and validity
- _resolve_schema_params() injection logic
- Memory Schema grouping logic (Entity as fallback only)
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Ensure server/ is on sys.path
# ---------------------------------------------------------------------------
SERVER_DIR = __file__.rsplit('/', 2)[0]  # .../graphiti-web-service/server
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


# ===========================================================================
# Test 1: DEFAULT_ENTITY_TYPES structure
# ===========================================================================


class TestDefaultEntityTypes:
    """Validate DEFAULT_ENTITY_TYPES dict structure."""

    def test_default_types_exist(self):
        from graph_service.models import DEFAULT_ENTITY_TYPES

        assert isinstance(DEFAULT_ENTITY_TYPES, dict)
        assert len(DEFAULT_ENTITY_TYPES) > 0

    def test_expected_type_names(self):
        from graph_service.models import DEFAULT_ENTITY_TYPES

        expected = {'Person', 'Organization', 'Location', 'Object', 'Document', 'Event', 'Topic'}
        assert set(DEFAULT_ENTITY_TYPES.keys()) == expected

    def test_all_values_are_pydantic_models(self):
        from graph_service.models import DEFAULT_ENTITY_TYPES

        for name, model_cls in DEFAULT_ENTITY_TYPES.items():
            assert issubclass(model_cls, BaseModel), f'{name} is not a BaseModel subclass'
            assert model_cls.__name__ == name, f'Model name mismatch: {model_cls.__name__} != {name}'

    def test_docstrings_present(self):
        """Each type should have a docstring for LLM classification."""
        from graph_service.models import DEFAULT_ENTITY_TYPES

        for name, model_cls in DEFAULT_ENTITY_TYPES.items():
            doc = model_cls.__doc__ or ''
            assert len(doc.strip()) > 10, f'{name} should have a meaningful docstring'

    def test_no_attributes_in_defaults(self):
        """Default types should not trigger attribute extraction."""
        from graph_service.models import DEFAULT_ENTITY_TYPES

        for name, model_cls in DEFAULT_ENTITY_TYPES.items():
            # Should only have standard Pydantic fields, no custom annotations
            annotations = getattr(model_cls, '__annotations__', {})
            assert len(annotations) == 0, f'{name} should have no field annotations'


# ===========================================================================
# Test 2: _resolve_schema_params() injection
# ===========================================================================


class TestResolveSchemaParams:
    """Test the schema parameter resolution with default type injection."""

    @pytest.mark.asyncio
    async def test_no_schema_returns_defaults(self):
        """schema_id=None should return DEFAULT_ENTITY_TYPES."""
        from graph_service.models import DEFAULT_ENTITY_TYPES
        from graph_service.routers.ingest import _resolve_schema_params

        entity_types, edge_types, custom = await _resolve_schema_params(None)

        assert entity_types == DEFAULT_ENTITY_TYPES
        assert edge_types is None
        assert custom is None

    @pytest.mark.asyncio
    async def test_empty_schema_falls_back_to_defaults(self):
        """Schema with empty entity_types should fall back to defaults."""
        from graph_service.models import DEFAULT_ENTITY_TYPES
        from graph_service.routers.ingest import _resolve_schema_params

        mock_schema = {
            'name': 'Empty Schema',
            'description': '',
            'entity_types': [],
            'edge_types': [],
            'custom_instructions': '',
        }

        with (
            patch('graph_service.config.get_settings') as mock_settings,
            patch('graph_service.models.get_schema', new_callable=AsyncMock) as mock_get,
            patch('graph_service.models.build_extraction_params') as mock_build,
        ):
            mock_settings.return_value = MagicMock(postgres_age_dsn='postgres://test')
            mock_get.return_value = mock_schema
            mock_build.return_value = ({}, {}, None)

            entity_types, edge_types, custom = await _resolve_schema_params(1)

            assert entity_types == DEFAULT_ENTITY_TYPES
            assert edge_types == {}
            assert custom is None

    @pytest.mark.asyncio
    async def test_custom_schema_takes_priority(self):
        """Custom schema with entity_types should NOT use defaults."""
        from graph_service.routers.ingest import _resolve_schema_params

        custom_entity = MagicMock()
        mock_schema = {
            'name': 'Custom Schema',
            'description': '',
            'entity_types': [{'name': 'CustomType', 'description': 'test'}],
            'edge_types': [],
            'custom_instructions': '',
        }

        with (
            patch('graph_service.config.get_settings') as mock_settings,
            patch('graph_service.models.get_schema', new_callable=AsyncMock) as mock_get,
            patch('graph_service.models.build_extraction_params') as mock_build,
        ):
            mock_settings.return_value = MagicMock(postgres_age_dsn='postgres://test')
            mock_get.return_value = mock_schema
            mock_build.return_value = ({'CustomType': custom_entity}, {}, None)

            entity_types, _edge_types, custom = await _resolve_schema_params(2)

            assert entity_types == {'CustomType': custom_entity}
            assert 'CustomType' in entity_types

    @pytest.mark.asyncio
    async def test_missing_schema_returns_defaults(self):
        """Non-existent schema_id should fall back to defaults."""
        from graph_service.models import DEFAULT_ENTITY_TYPES
        from graph_service.routers.ingest import _resolve_schema_params

        with (
            patch('graph_service.config.get_settings') as mock_settings,
            patch('graph_service.models.get_schema', new_callable=AsyncMock) as mock_get,
        ):
            mock_settings.return_value = MagicMock(postgres_age_dsn='postgres://test')
            mock_get.return_value = None

            entity_types, edge_types, custom = await _resolve_schema_params(999)

            assert entity_types == DEFAULT_ENTITY_TYPES
            assert edge_types is None
            assert custom is None


# ===========================================================================
# Test 3: Memory Schema grouping logic
# ===========================================================================


class TestMemorySchemaGrouping:
    """Test entity grouping by specific labels with Entity as fallback."""

    def test_entity_with_specific_label_goes_to_specific_card(self):
        """['Entity', 'Person'] should only appear in PERSON card."""
        # Simulate the grouping logic
        records = [
            {'uuid': '1', 'name': 'Alice', 'labels': ['Entity', 'Person']},
            {'uuid': '2', 'name': 'Google', 'labels': ['Entity', 'Organization']},
        ]

        specific_label_counts: dict[str, int] = {}
        specific_label_items: dict[str, list[dict]] = {}
        fallback_uuids: set[str] = set()

        for record in records:
            uid = record['uuid']
            specific = set(record['labels']) - {'Entity'}
            if specific:
                for lbl in specific:
                    specific_label_counts[lbl] = specific_label_counts.get(lbl, 0) + 1
                    specific_label_items.setdefault(lbl, []).append({'id': uid, 'label': record['name']})
            else:
                fallback_uuids.add(uid)

        assert 'Person' in specific_label_items
        assert 'Organization' in specific_label_items
        assert len(fallback_uuids) == 0

    def test_entity_only_label_goes_to_fallback(self):
        """['Entity'] should only appear in ENTITY fallback card."""
        records = [
            {'uuid': '3', 'name': 'Unknown Thing', 'labels': ['Entity']},
        ]

        specific_label_counts: dict[str, int] = {}
        specific_label_items: dict[str, list[dict]] = {}
        fallback_uuids: set[str] = set()

        for record in records:
            uid = record['uuid']
            specific = set(record['labels']) - {'Entity'}
            if specific:
                for lbl in specific:
                    specific_label_counts[lbl] = specific_label_counts.get(lbl, 0) + 1
                    specific_label_items.setdefault(lbl, []).append({'id': uid, 'label': record['name']})
            else:
                fallback_uuids.add(uid)

        assert len(specific_label_items) == 0
        assert len(fallback_uuids) == 1
        assert '3' in fallback_uuids

    def test_mixed_entities_grouping(self):
        """Mix of specific and fallback entities."""
        records = [
            {'uuid': '1', 'name': 'Alice', 'labels': ['Entity', 'Person']},
            {'uuid': '2', 'name': 'Google', 'labels': ['Entity', 'Organization']},
            {'uuid': '3', 'name': 'Unknown', 'labels': ['Entity']},
            {'uuid': '4', 'name': 'Paris', 'labels': ['Entity', 'Location']},
        ]

        specific_label_counts: dict[str, int] = {}
        specific_label_items: dict[str, list[dict]] = {}
        fallback_uuids: set[str] = set()

        for record in records:
            uid = record['uuid']
            specific = set(record['labels']) - {'Entity'}
            if specific:
                for lbl in specific:
                    specific_label_counts[lbl] = specific_label_counts.get(lbl, 0) + 1
                    specific_label_items.setdefault(lbl, []).append({'id': uid, 'label': record['name']})
            else:
                fallback_uuids.add(uid)

        assert set(specific_label_items.keys()) == {'Person', 'Organization', 'Location'}
        assert fallback_uuids == {'3'}
        # Each specific card has exactly 1 entity
        assert len(specific_label_items['Person']) == 1
        assert len(specific_label_items['Organization']) == 1
        assert len(specific_label_items['Location']) == 1

    def test_multiple_specific_labels_one_entity(self):
        """Entity with multiple specific labels appears in each relevant card."""
        records = [
            {'uuid': '1', 'name': 'Conference', 'labels': ['Entity', 'Event', 'Topic']},
        ]

        specific_label_counts: dict[str, int] = {}
        specific_label_items: dict[str, list[dict]] = {}
        fallback_uuids: set[str] = set()

        for record in records:
            uid = record['uuid']
            specific = set(record['labels']) - {'Entity'}
            if specific:
                for lbl in specific:
                    specific_label_counts[lbl] = specific_label_counts.get(lbl, 0) + 1
                    specific_label_items.setdefault(lbl, []).append({'id': uid, 'label': record['name']})
            else:
                fallback_uuids.add(uid)

        assert 'Event' in specific_label_items
        assert 'Topic' in specific_label_items
        assert len(fallback_uuids) == 0


# ===========================================================================
# Test 4: build_extraction_params passthrough
# ===========================================================================


class TestBuildExtractionParams:
    """Verify build_extraction_params handles edge cases."""

    def test_empty_schema_returns_empty(self):
        from graph_service.models import build_extraction_params

        result = build_extraction_params({
            'name': 'Empty',
            'entity_types': [],
            'edge_types': [],
        })
        entity_types, edge_types, custom = result
        assert entity_types == {}
        assert edge_types == {}
        assert custom is None

    def test_schema_with_entity_types(self):
        from graph_service.models import build_extraction_params

        schema = {
            'name': 'Test',
            'entity_types': [
                {'name': 'Person', 'description': 'A person', 'attributes': []},
            ],
            'edge_types': [],
            'custom_instructions': 'Be precise.',
        }
        entity_types, edge_types, custom = build_extraction_params(schema)
        assert 'Person' in entity_types
        assert issubclass(entity_types['Person'], BaseModel)
        assert custom == 'Be precise.'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
