# server/graph_service/routers/chat.py
import re

from fastapi import APIRouter, status

from graph_service.dto.chat import ChatRequestDTO, ChatResponseDTO
from graph_service.zep_graphiti import ZepGraphitiDep, get_fact_result_from_edge

router = APIRouter()

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


@router.post('/chat', status_code=status.HTTP_200_OK)
async def chat(request: ChatRequestDTO, graphiti: ZepGraphitiDep):
    # 1. Search graph based on context
    group_ids = None
    ctx = request.context
    if ctx and ctx.context_id and ctx.context_type == 'group':
        group_ids = [ctx.context_id]

    # Search using current message only — concatenating history dilutes
    # the embedding semantics especially for mixed-language queries
    query = request.message

    relevant_edges = await graphiti.search(
        group_ids=group_ids,
        query=query,
        num_results=10,
    )

    # Fallback: extract English/technical keywords and search again
    # MiniLM has weak cross-language semantics — a Chinese question about
    # "Sigma.js" may not embed close to the stored English fact text.
    if not relevant_edges:
        keywords = re.findall(r'[A-Za-z][\w.\-]+', query)
        if keywords:
            keyword_query = ' '.join(keywords)
            relevant_edges = await graphiti.search(
                group_ids=group_ids,
                query=keyword_query,
                num_results=10,
            )

    # 2. Build search results text, context info, and scope hint
    search_text = _build_search_results_text(relevant_edges)
    context_info = _build_context_info(request.context)
    scope_hint = (
        '- 搜索范围：仅限当前分组的数据'
        if group_ids
        else '- 搜索范围：全部分组'
    )

    # 3. Build LLM messages
    llm_messages = _build_messages(
        search_text,
        context_info,
        scope_hint,
        [h.model_dump() for h in request.history],
        request.message,
    )

    # 4. Call LLM
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

    # 5. Extract answer text — generate_response returns a parsed dict
    answer = response.get('answer', '') or response.get('content', '') or str(response)

    return ChatResponseDTO(answer=answer)