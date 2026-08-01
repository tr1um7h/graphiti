# server/graph_service/dto/chat.py
from pydantic import BaseModel, Field


class ChatContextDTO(BaseModel):
    context_id: str | None = None
    context_type: str | None = None  # 'group' | 'node' | 'edge' | 'document'
    context_name: str | None = None


class ChatMessageDTO(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str


class ChatRequestDTO(BaseModel):
    message: str
    context: ChatContextDTO = Field(default_factory=ChatContextDTO)
    history: list[ChatMessageDTO] = Field(default_factory=list)


class ChatResponseDTO(BaseModel):
    answer: str
