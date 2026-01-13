# knowledge/repository.py
import pymysql
from datetime import datetime
from knowledge.models import KnowledgeCandidate

def upsert_candidate(candidate):
    # TODO: Strato SQL upsert
    pass


def get_candidates(limit: int = 50):
    # TODO: SELECT * FROM knowledge_candidates
    return []


def approve_candidate(candidate_id: int):
    # TODO: move to knowledge_base
    pass

def get_connection():
    return pymysql.connect(
        host="database-5018961190.webspace-host.com",
        user="dbu1764978",
        password="AskYellow_20_25",
        database="dbs14939670",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )
def upsert_candidate(candidate: KnowledgeCandidate):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO knowledge_candidates
                (question, answer_raw, source, confidence_score,
                 occurrence_count, status, created_at, last_seen_at)
                VALUES (%s,%s,%s,%s,1,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    occurrence_count = occurrence_count + 1,
                    last_seen_at = %s,
                    confidence_score = GREATEST(confidence_score, %s)
            """, (
                candidate.question,
                candidate.answer_raw,
                candidate.source.value,
                candidate.confidence_score,
                candidate.status.value,
                candidate.created_at,
                candidate.last_seen_at,
                datetime.utcnow(),
                candidate.confidence_score
            ))
    finally:
        conn.close()
def get_candidates(limit: int = 50):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM knowledge_candidates
                WHERE status = 'candidate'
                ORDER BY occurrence_count DESC, last_seen_at DESC
                LIMIT %s
            """, (limit,))
            return cur.fetchall()
    finally:
        conn.close()

def approve_candidate(candidate_id: int, approved_by: str = "admin"):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT question, answer_raw
                FROM knowledge_candidates
                WHERE id = %s
            """, (candidate_id,))
            row = cur.fetchone()

            if not row:
                return False

            cur.execute("""
                INSERT INTO knowledge_base
                (question, answer, approved_by, approved_at)
                VALUES (%s,%s,%s,%s)
            """, (
                row["question"],
                row["answer_raw"],
                approved_by,
                datetime.utcnow()
            ))

            cur.execute("""
                UPDATE knowledge_candidates
                SET status = 'approved'
                WHERE id = %s
            """, (candidate_id,))

            return True
    finally:
        conn.close()
