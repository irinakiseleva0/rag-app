from typing import Literal
from pydantic import BaseModel, Field


class DocumentInfo(BaseModel):
    id: str
    filename: str
    n_chunks: int
    uploaded_at: str 


class Settings(BaseModel):
    chunk_size: int = Field(gt=0, le=10_000)
    overlap_percent: int = Field(ge=0, le=99)
    top_k: int = Field(ge=1, le=50)


class Reference(BaseModel):
    chunk_id: str
    filename: str
    chunk_index: int
    char_start: int
    char_end: int
    text: str
    score: float


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1)
    doc_ids: list[str] = []
    top_k: int = Field(ge=1, le=50)


class RetrieveResult(BaseModel):
    chunks: list[Reference]


class AskResult(BaseModel):
    status: Literal["answered", "not_found", "error"]
    answer: str
    references: list[Reference]
    error: str | None = None


class LLMAnswer(BaseModel):
    status: Literal["answered", "not_found"]
    answer: str
    used_chunk_ids: list[str]
