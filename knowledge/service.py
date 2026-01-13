# knowledge/service.py
from datetime import datetime
from knowledge.models import KnowledgeCandidate, KnowledgeSource, KnowledgeStatus
from knowledge.repository import upsert_candidate

def evaluate_candidate(candidate: KnowledgeCandidate) -> KnowledgeStatus:
    if candidate.confidence_score >= 0.85 and candidate.occurrence_count >= 3:
        return KnowledgeStatus.approved
    return KnowledgeStatus.rejected
def ingest_candidate(
    question: str,
    answer_raw: str,
    source: KnowledgeSource,
    confidence_score: float = 0.0
):
    """
    Verzamelt mogelijke kennis zonder goedkeuring.
    """
    candidate = KnowledgeCandidate(
        id=None,
        question=question,
        answer_raw=answer_raw,
        answer_clean=None,
        source=source,
        confidence_score=confidence_score,
        occurrence_count=1,
        status=KnowledgeStatus.candidate,
        created_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow()
    )

    upsert_candidate(candidate)
