# server/graph_service/routers/chat.py
import re

from fastapi import APIRouter, status

from graphiti_core.driver.postgres_age.records import entity_edge_from_row
from graphiti_core.edges import EntityEdge
from graphiti_core.search.search_config import (
    EdgeReranker,
    EdgeSearchConfig,
    EdgeSearchMethod,
    NodeReranker,
    NodeSearchConfig,
    NodeSearchMethod,
    SearchConfig,
)
from graph_service.dto.chat import ChatRequestDTO, ChatResponseDTO
from graph_service.zep_graphiti import ZepGraphitiDep, get_fact_result_from_edge
from graph_service.config import get_settings


def _build_chat_search_config() -> SearchConfig:
    """Build SearchConfig from environment-configured parameters."""
    s = get_settings()
    return SearchConfig(
        edge_config=EdgeSearchConfig(
            search_methods=[
                EdgeSearchMethod.bm25,
                EdgeSearchMethod.cosine_similarity,
                EdgeSearchMethod.bfs,
            ],
            reranker=EdgeReranker.rrf,
            sim_min_score=s.chat_sim_min_score,
            bfs_max_depth=s.chat_bfs_max_depth,
        ),
        node_config=NodeSearchConfig(
            search_methods=[
                NodeSearchMethod.bm25,
                NodeSearchMethod.cosine_similarity,
                NodeSearchMethod.bfs,
            ],
            reranker=NodeReranker.rrf,
            sim_min_score=s.chat_sim_min_score,
            bfs_max_depth=s.chat_bfs_max_depth,
        ),
        limit=s.chat_search_limit,
    )

router = APIRouter()

# Search config is built per-request via _build_chat_search_config().
# Override defaults via .env:
#   CHAT_SIM_MIN_SCORE  — cosine similarity threshold (default 0.2)
#   CHAT_SEARCH_LIMIT   — max edges per search channel (default 10)
#   CHAT_BFS_MAX_DEPTH  — BFS traversal depth (default 3)

MAX_CONTEXT_EDGES = 15

CHAT_SYSTEM_PROMPT = """你是一个知识图谱助手。你帮助用户验证和探索他们的知识图谱数据。

当前上下文：
- 分组(group): {context_info}
{scope_hint}

图谱搜索结果：
{search_results}

回答规则：
1. 优先根据搜索结果回答。如果搜索结果为空，说明该分组中暂无相关数据。
2. 用户询问当前分组时，直接告诉上下文中的分组信息。
3. 回答简洁、准确。如果数据不完整，指出可能的遗漏。
4. 请以json格式返回，包含answer字段。"""


def _build_search_results_text(edges) -> str:
    if not edges:
        return '（未找到相关结果）'

    lines = []
    for edge in edges:
        fact = get_fact_result_from_edge(edge)
        lines.append(f'- {fact.name}: {fact.fact}')
    return '\n'.join(lines)


def _build_context_info(ctx) -> str:
    if not ctx:
        return '未指定'
    parts = []
    if ctx.context_id:
        parts.append(f"ID={ctx.context_id}")
    if ctx.context_type:
        parts.append(f"类型={ctx.context_type}")
    if ctx.context_name:
        parts.append(f"名称={ctx.context_name}")
    return ', '.join(parts) if parts else '未指定'


def _build_messages(search_text: str, context_info: str, scope_hint: str, history: list, user_message: str) -> list:
    system_content = CHAT_SYSTEM_PROMPT.format(
        search_results=search_text, context_info=context_info, scope_hint=scope_hint,
    )
    messages = [{'role': 'system', 'content': system_content}]

    for h in history:
        messages.append({'role': h['role'], 'content': h['content']})

    messages.append({'role': 'user', 'content': user_message})

    return messages


async def _entity_link_search(
    graphiti: ZepGraphitiDep,
    query: str,
    group_ids: list[str] | None,
) -> list[EntityEdge]:
    """Find edges by matching entity names in the query to graph nodes,
    then traversing their connecting edges.

    This bypasses embedding/BM25 limitations entirely. It directly links
    entity names mentioned in the query to nodes in the target group(s),
    making it language-independent and robust for "relationship between X
    and Y" queries where BM25 AND-semantics and embedding thresholds fail.
    """
    if not group_ids:
        return []

    driver = graphiti.driver

    # 1. Load node names + uuids in the target group(s)
    nodes_result, _, _ = await driver.execute_query(
        """
        SELECT uuid, name FROM entity_nodes
        WHERE group_id = ANY(%(group_ids)s)
        """,
        params={'group_ids': group_ids},
    )

    if not nodes_result:
        return []

    # 2. Match: which nodes are mentioned in the query?
    #    (a) Node name appears verbatim in the query — handles Chinese,
    #        mixed-language, and full-name lookups.
    #    (b) English/technical keyword from the query matches the node name
    #        — handles abbreviations and partial matches.
    query_lower = query.lower()
    keywords = [kw.lower() for kw in re.findall(r'[A-Za-z][\w.\-]+', query)]

    matched_uuids: set[str] = set()
    for row in nodes_result:
        name = (row['name'] or '').strip()
        if not name:
            continue
        name_lower = name.lower()
        if name_lower in query_lower:
            matched_uuids.add(row['uuid'])
        elif any(kw and (kw in name_lower or name_lower in kw) for kw in keywords):
            matched_uuids.add(row['uuid'])

    if not matched_uuids:
        return []

    # 3. Find edges connecting matched nodes
    uuid_list = list(matched_uuids)
    edges_result, _, _ = await driver.execute_query(
        """
        SELECT *
        FROM entity_edges
        WHERE group_id = ANY(%(group_ids)s)
          AND (source_node_uuid = ANY(%(node_uuids)s)
               OR target_node_uuid = ANY(%(node_uuids)s))
        LIMIT %(limit)s
        """,
        params={'group_ids': group_ids, 'node_uuids': uuid_list, 'limit': MAX_CONTEXT_EDGES},
    )

    return [entity_edge_from_row(row) for row in (edges_result or [])]


@router.post('/chat', status_code=status.HTTP_200_OK)
async def chat(request: ChatRequestDTO, graphiti: ZepGraphitiDep):
    # 1. Determine search scope from context
    group_ids = None
    ctx = request.context
    if ctx and ctx.context_id and ctx.context_type == 'group':
        group_ids = [ctx.context_id]

    query = request.message

    # 2. Entity linking: match entity names in the query to graph nodes,
    #    then traverse their edges. This is the most reliable path for
    #    "relationship between X and Y" queries — language-independent
    #    and unaffected by embedding quality or BM25 AND-semantics.
    entity_linked_edges = await _entity_link_search(graphiti, query, group_ids)

    # 3. Hybrid search (BM25 + cosine + BFS) as a
    #    complementary channel for semantic matches that entity linking
    #    may miss (e.g. queries without specific entity names).
    hybrid_results = await graphiti.search_(
        query=query,
        config=_build_chat_search_config(),
        group_ids=group_ids,
    )
    hybrid_edges = hybrid_results.edges

    # 4. Merge: entity-linked edges first (higher precision), then hybrid
    #    edges, deduplicated by UUID.
    seen_uuids: set[str] = set()
    relevant_edges: list[EntityEdge] = []
    for edge in entity_linked_edges + hybrid_edges:
        if edge.uuid not in seen_uuids:
            seen_uuids.add(edge.uuid)
            relevant_edges.append(edge)
            if len(relevant_edges) >= MAX_CONTEXT_EDGES:
                break

    # 5. Build search results text, context info, and scope hint
    search_text = _build_search_results_text(relevant_edges)
    context_info = _build_context_info(request.context)
    scope_hint = (
        '- 搜索范围：仅限当前分组的数据'
        if group_ids
        else '- 搜索范围：全部分组'
    )

    # 6. Build LLM messages
    llm_messages = _build_messages(
        search_text,
        context_info,
        scope_hint,
        [h.model_dump() for h in request.history],
        request.message,
    )

    # 7. Call LLM
    from graphiti_core.llm_client.config import ModelSize
    from graphiti_core.prompts.models import Message

    core_messages = [
        Message(role=m['role'], content=m['content']) for m in llm_messages
    ]

    response = await graphiti.llm_client.generate_response(
        messages=core_messages,
        model_size=ModelSize.medium,
        prompt_name='chat_qna',
    )

    # 8. Extract answer text — generate_response returns a parsed dict
    answer = response.get('answer', '') or response.get('content', '') or str(response)

    return ChatResponseDTO(answer=answer)
