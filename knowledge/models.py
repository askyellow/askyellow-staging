# knowledge/models.py
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class KnowledgeSource(str, Enum):
    chat = "chat"
    search = "search"


class KnowledgeStatus(str, Enum):
    candidate = "candidate"
    approved = "approved"
    rejected = "rejected"


@dataclass
class KnowledgeCandidate:
    id: Optional[int]
    question: str
    answer_raw: str
    answer_clean: Optional[str]
    source: KnowledgeSource
    confidence_score: float
    occurrence_count: int
    status: KnowledgeStatus
    created_at: datetime
    last_seen_at: datetime
