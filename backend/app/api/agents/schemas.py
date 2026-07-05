"""
Pydantic schemas for Agent API endpoints.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# ==================== Request Schemas ====================

class AgentCreate(BaseModel):
    """Agent creation request."""
    name: str = Field(..., max_length=255)
    system_prompt: str = Field(..., max_length=50000)
    model_provider: str = Field(..., max_length=100)
    model_name: str = Field(..., max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    temperature: float = 0.7
    use_rag: bool = True
    rag_top_k: int = 5
    skills: Optional[list[dict]] = None
    is_public: bool = False
    available_in_chat: bool = False
    source_ids: Optional[list[str]] = None
    suggestions: Optional[list[dict]] = None


class AgentUpdate(BaseModel):
    """Agent update request."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    system_prompt: Optional[str] = Field(None, max_length=50000)
    model_provider: Optional[str] = Field(None, max_length=100)
    model_name: Optional[str] = Field(None, max_length=200)
    temperature: Optional[float] = None
    use_rag: Optional[bool] = None
    rag_top_k: Optional[int] = None
    skills: Optional[list[dict]] = None
    is_public: Optional[bool] = None
    available_in_chat: Optional[bool] = None
    source_ids: Optional[list[str]] = None
    suggestions: Optional[list[dict]] = None


class AgentDuplicate(BaseModel):
    """Agent duplication request."""
    new_name: str = Field(..., max_length=255)


class InvokeRequest(BaseModel):
    """Agent invocation request."""
    message: str = Field(..., max_length=32000)
    context: Optional[dict] = None

    @field_validator("context")
    @classmethod
    def validate_context_size(cls, v):
        if v is not None and len(v) > 10:
            raise ValueError("Context must have at most 10 keys")
        return v


# ==================== Response Schemas ====================

class AgentResponse(BaseModel):
    """Agent response."""
    id: str
    agent_id: Optional[str]  # URL-safe identifier auto-generated from name
    extension_id: Optional[str] = None  # FK to extension (null for user-created)
    name: str
    description: Optional[str]
    system_prompt: str
    model_provider: str
    model_name: str
    temperature: float
    use_rag: bool
    rag_top_k: int
    skills: list
    suggestions: Optional[list[dict]] = None
    is_public: bool
    available_in_chat: bool = False
    has_api_key: bool
    source_ids: list[str]
    library_ids: list[str] = []  # Libraries bound via AgentLibrary
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ApiKeyResponse(BaseModel):
    """API key generation response."""
    api_key: str
    message: str
    is_public: bool = True
    has_api_key: bool = True


class SkillDefinition(BaseModel):
    """Skill definition."""
    type: str
    name: str
    description: str
    config_schema: dict


class SkillsResponse(BaseModel):
    """Available skills response."""
    skills: dict[str, SkillDefinition]


class RAGSourceResponse(BaseModel):
    """RAG source attribution in invoke response."""
    source_id: str
    source_name: str
    url: str
    title: str
    score: float
    preview: str


class InvokeResponse(BaseModel):
    """Agent invocation response."""
    success: bool
    response: str
    sources: list[RAGSourceResponse] = []
    skills_used: list[str] = []
    total_skill_calls: int = 0
    execution_time_ms: Optional[int] = None
    error: Optional[str] = None


class TurnInfo(BaseModel):
    """Information about a single turn in agent execution."""
    role: str
    content: str
    skill_id: Optional[str] = None


class DetailedInvokeResponse(BaseModel):
    """Detailed agent invocation response with turn history."""
    success: bool
    response: str
    turns: list[TurnInfo] = []
    total_skill_calls: int = 0
    execution_time_ms: Optional[int] = None
    error: Optional[str] = None


# ==================== Agent Query Schemas ====================

class AgentQueryRequest(BaseModel):
    """Agent query request — stateless RAG-grounded Q&A."""
    query: str = Field(..., max_length=8000, description="The question to ask the agent")
    session_id: Optional[str] = Field(
        None,
        max_length=128,
        description="Optional session identifier (reserved for future session support)",
    )
    filters: Optional[dict] = Field(
        None,
        description="Optional metadata filters to narrow knowledge retrieval",
    )


class AgentQuerySourceItem(BaseModel):
    """A knowledge source referenced in a query response."""
    source_id: str
    source_name: str
    url: str
    title: str
    score: float
    preview: str


class AgentQueryResponse(BaseModel):
    """Agent query response with synthesized answer and source attribution."""
    answer: str
    sources: list[AgentQuerySourceItem] = []
    query: str
    model: str
    agent_id: str
