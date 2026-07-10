# server/graph_service/routers/chat.py
from fastapi import APIRouter, status

from graph_service.dto.chat import ChatRequestDTO, ChatResponseDTO
from graph_service.zep_graphiti import ZepGraphitiDep, get_fact_result_from_edge

router = APIRouter()

CHAT_SYSTEM_PROMPT = """你是一个知识图谱助手。你帮助用户验证和探索他们的知识图谱数据。
以下是图谱中的相关信息。

搜索结果：
{search_results}

基于提供的图谱数据回答问题。如果用户询问数据完整性，指出可能的遗漏点。
回答保持简洁。"""


def _build_search_results_text(edges) -> str:
    if not edges:
        return '（未找到相关结果）'

    lines = []
    for edge in edges:
        fact = get_fact_result_from_edge(edge)
        lines.append(f'- {fact.name}: {fact.fact}')
    return '\n'.join(lines)


def _build_messages(search_text: str, history: list, user_message: str) -> list:
    system_content = CHAT_SYSTEM_PROMPT.format(search_results=search_text)
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

    # Use last few history messages + current message for better search query
    query = request.message
    if request.history:
        recent = [h.content for h in request.history[-4:]]
        query = ' '.join(recent) + ' ' + request.message

    relevant_edges = await graphiti.search(
        group_ids=group_ids,
        query=query,
        num_results=10,
    )

    # 2. Build search results text
    search_text = _build_search_results_text(relevant_edges)

    # 3. Build LLM messages
    llm_messages = _build_messages(
        search_text,
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

    # 5. Extract answer text
    answer = response.get('content', '') or response.get('response', '') or str(response)

    return ChatResponseDTO(answer=answer)