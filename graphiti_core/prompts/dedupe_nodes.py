"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from typing import Any, Protocol, TypedDict

from pydantic import BaseModel, Field

from .models import Message, PromptFunction, PromptVersion
from .prompt_helpers import to_prompt_json


class NodeDuplicate(BaseModel):
    id: int = Field(..., description='integer id of the entity')
    name: str = Field(
        ...,
        description='Name of the entity. Should be the most complete and descriptive name of the entity. Do not include any JSON formatting in the Entity name such as {}.',
    )
    duplicate_candidate_id: int = Field(
        ...,
        description='candidate_id of the matching EXISTING ENTITY, or -1 if no duplicate exists.',
    )
    # OWL ontology
    type_validation: str = Field(
        default='valid',
        description='OWL ontology validation result: "valid", "type_mismatch", or "unknown_type"',
    )
    matched_ontology_type: str | None = Field(
        default=None,
        description='The matched ontology type from the predefined list, if any',
    )


class NodeResolutions(BaseModel):
    entity_resolutions: list[NodeDuplicate] = Field(..., description='List of resolved nodes')


class Prompt(Protocol):
    node: PromptVersion
    node_list: PromptVersion
    nodes: PromptVersion


class Versions(TypedDict):
    node: PromptFunction
    node_list: PromptFunction
    nodes: PromptFunction


def node(context: dict[str, Any]) -> list[Message]:
    return [
        Message(
            role='system',
            content='You are an entity deduplication assistant. '
            'NEVER fabricate entity names or mark distinct entities as duplicates.',
        ),
        Message(
            role='user',
            content=f"""
<PREVIOUS MESSAGES>
{to_prompt_json(context['previous_episodes'])}
</PREVIOUS MESSAGES>

<CURRENT MESSAGE>
{context['episode_content']}
</CURRENT MESSAGE>

<NEW ENTITY>
{to_prompt_json(context['extracted_node'])}
</NEW ENTITY>

<ENTITY TYPE DESCRIPTION>
{to_prompt_json(context['entity_type_description'])}
</ENTITY TYPE DESCRIPTION>

<EXISTING ENTITIES>
{to_prompt_json(context['existing_nodes'])}
</EXISTING ENTITIES>

Entities should only be considered duplicates if they refer to the *same real-world object or concept*.
Semantic Equivalence: if a descriptive label in EXISTING ENTITIES clearly refers to a named entity in context, treat them as duplicates.

NEVER mark entities as duplicates if:
- They are related but distinct.
- They have similar names or purposes but refer to separate instances or concepts.

Task:
1. Compare the NEW ENTITY against each EXISTING ENTITY (identified by `candidate_id`).
2. If it refers to the same real-world object or concept, return the `candidate_id` of that match.
3. Return `duplicate_candidate_id = -1` when there is no match or you are unsure.

<EXAMPLE>
NEW ENTITY: "Sam" (Person)
EXISTING ENTITIES: [{{"candidate_id": 0, "name": "Sam", "entity_types": ["Person"], "summary": "Sam enjoys hiking and photography"}}]
Result: duplicate_candidate_id = 0 (same person referenced in conversation)

NEW ENTITY: "NYC"
EXISTING ENTITIES: [{{"candidate_id": 0, "name": "New York City", "entity_types": ["Location"]}}, {{"candidate_id": 1, "name": "New York Knicks", "entity_types": ["Organization"]}}]
Result: duplicate_candidate_id = 0 (same location, abbreviated name)

NEW ENTITY: "Java" (programming language)
EXISTING ENTITIES: [{{"candidate_id": 0, "name": "Java", "entity_types": ["Location"], "summary": "An island in Indonesia"}}]
Result: duplicate_candidate_id = -1 (same name but distinct real-world things)

NEW ENTITY: "Marco's car"
EXISTING ENTITIES: [{{"candidate_id": 0, "name": "Marco's vehicle", "entity_types": ["Entity"], "summary": "Marco drives a red sedan."}}]
Result: duplicate_candidate_id = 0 (synonym — "car" and "vehicle" refer to the same thing, same possessor)
</EXAMPLE>
""",
        ),
    ]


def nodes(context: dict[str, Any]) -> list[Message]:
    # Get allowed entity types from context
    allowed_types = context.get('allowed_entity_types', ['Entity'])

    return [
        Message(
            role='system',
            content='You are an entity deduplication assistant with OWL ontology validation. '
            'NEVER fabricate entity names or mark distinct entities as duplicates.',
        ),
        Message(
            role='user',
            content=f"""
<PREVIOUS MESSAGES>
{to_prompt_json(context['previous_episodes'])}
</PREVIOUS MESSAGES>

<CURRENT MESSAGE>
{context['episode_content']}
</CURRENT MESSAGE>

<ENTITIES>
{to_prompt_json(context['extracted_nodes'])}
</ENTITIES>

<EXISTING ENTITIES>
{to_prompt_json(context['existing_nodes'])}
</EXISTING ENTITIES>

<ONTOLOGY CONSTRAINTS>
Allowed Entity Types: {allowed_types}

Stage 5 - OWL Ontology Validation:
Before resolving duplicates, validate each extracted entity against the ontology:

1. Type Compliance Check:
   - Check if the entity's `entity_type` overlaps with Allowed Entity Types
   - If type is NOT in the allowed list → type_validation: "unknown_type"
   - If entity type contradicts existing entity of same name → type_validation: "type_mismatch"
   - If type is valid → type_validation: "valid"

2. Duplicate Validation Rules:
   - ONLY consider duplicates if types are compatible
   - A "Person" cannot be duplicate of an "Organization" even with same name
   - A generic "Entity" CAN be duplicate with a more specific type (Person, Location, etc.)

3. Response Requirements:
   For each entity, provide:
   - id: entity ID
   - name: best full name
   - duplicate_candidate_id: matching candidate or -1
   - type_validation: "valid" | "type_mismatch" | "unknown_type"
   - matched_ontology_type: the matched type from allowed list, or null if unknown_type

Examples:
- Entity "John" (type: ["Person"]) vs existing "John" (type: ["Organization"]) → type_mismatch
- Entity "Apple" (type: ["Entity"]) vs existing "Apple Inc" (type: ["Organization"]) → valid duplicate
- Entity "Mars" (type: ["Deity"]) when Allowed=[Entity, Person, Location] → unknown_type
</ONTOLOGY CONSTRAINTS>

Each of the above ENTITIES was extracted from the CURRENT MESSAGE.
For each entity, determine if it is a duplicate of any EXISTING ENTITY.
Entities should only be considered duplicates if they refer to the *same real-world object or concept*.

NEVER mark entities as duplicates if:
- They are related but distinct.
- They have similar names or purposes but refer to separate instances or concepts.

Task:
ENTITIES contains {len(context['extracted_nodes'])} entities with IDs 0 through {len(context['extracted_nodes']) - 1}.
Your response MUST include EXACTLY {len(context['extracted_nodes'])} resolutions with IDs 0 through {len(context['extracted_nodes']) - 1}. Do not skip or add IDs.

For every entity, provide:
- `id`: integer id from ENTITIES
- `name`: the best full name for the entity (preserve the original name unless a duplicate has a more complete name)
- `duplicate_candidate_id`: the `candidate_id` of the EXISTING ENTITY that is the best duplicate match, or -1 if there is no duplicate
- `type_validation`: "valid", "type_mismatch", or "unknown_type"
- `matched_ontology_type`: the matched type from allowed list, or null

<EXAMPLE>
ENTITY: "Sam" (Person)
EXISTING ENTITIES: [{{"candidate_id": 0, "name": "Sam", "entity_types": ["Person"], "summary": "Sam enjoys hiking and photography"}}]
Result: duplicate_candidate_id = 0, type_validation = "valid", matched_ontology_type = "Person"

ENTITY: "NYC"
EXISTING ENTITIES: [{{"candidate_id": 0, "name": "New York City", "entity_types": ["Location"]}}, {{"candidate_id": 1, "name": "New York Knicks", "entity_types": ["Organization"]}}]
Result: duplicate_candidate_id = 0, type_validation = "valid", matched_ontology_type = "Location"

ENTITY: "Java" (programming language)
EXISTING ENTITIES: [{{"candidate_id": 0, "name": "Java", "entity_types": ["Location"], "summary": "An island in Indonesia"}}]
Result: duplicate_candidate_id = -1, type_validation = "valid", matched_ontology_type = "Entity"

ENTITY: "Marco's car"
EXISTING ENTITIES: [{{"candidate_id": 0, "name": "Marco's vehicle", "entity_types": ["Entity"], "summary": "Marco drives a red sedan."}}]
Result: duplicate_candidate_id = 0, type_validation = "valid", matched_ontology_type = "Entity"

ENTITY: "Zeus" (type: ["Deity"]) when Allowed=[Entity, Person, Location]
Result: duplicate_candidate_id = -1, type_validation = "unknown_type", matched_ontology_type = null
</EXAMPLE>
""",
        ),
    ]


def node_list(context: dict[str, Any]) -> list[Message]:
    return [
        Message(
            role='system',
            content='You are an entity deduplication assistant that groups duplicate nodes by UUID.',
        ),
        Message(
            role='user',
            content=f"""
Given the following context, deduplicate a list of nodes:

<NODES>
{to_prompt_json(context['nodes'])}
</NODES>

Task:
1. Group nodes together such that all duplicate nodes are in the same list of uuids.
2. All duplicate uuids should be grouped together in the same list.
3. Also return a new summary that synthesizes the summaries into a new short summary.

Guidelines:
1. Each uuid from the list of nodes should appear EXACTLY once in your response.
2. If a node has no duplicates, it should appear in the response in a list of only one uuid.

<EXAMPLE>
Input nodes:
[
  {{"uuid": "a1", "name": "NYC", "summary": "New York City"}},
  {{"uuid": "b2", "name": "New York City", "summary": "The city of New York"}},
  {{"uuid": "c3", "name": "Los Angeles", "summary": "City in California"}}
]

Result:
[
  {{"uuids": ["a1", "b2"], "summary": "New York City, also known as NYC"}},
  {{"uuids": ["c3"], "summary": "City in California"}}
]
</EXAMPLE>
""",
        ),
    ]


versions: Versions = {'node': node, 'node_list': node_list, 'nodes': nodes}
