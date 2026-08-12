"""Retrieval policy, kept separate so semantic/vector retrieval can replace it later."""

import re
from datetime import datetime, timezone

from memory.models import MemoryRecord


class LexicalMemoryRetrieval:
    """Small ranked retrieval using scope, token overlap, importance, and recency."""

    def retrieve(self, query: str, records: list[MemoryRecord], presentation_id: str, limit: int = 5) -> list[dict]:
        terms = meaningful_terms(query)
        ranked = []
        for record in records:
            relevance = len(terms & meaningful_terms(str(record.content)))
            scope_bonus = 3.0 if record.presentation_id == presentation_id else 1.5 if record.type == "user_preference" else 0.0
            age_days = max(0, (datetime.now(timezone.utc) - record.updated_at).days)
            recency = 1.0 / (1.0 + age_days)
            score = relevance * 2.0 + record.importance + recency + scope_bonus
            if relevance or record.type == "working_memory":
                item = record.model_dump(mode="json")
                item["metadata"] = {**item["metadata"], "retrieval_score": round(score, 3)}
                ranked.append((score, item))
        return [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:limit]]


def meaningful_terms(text: str) -> set[str]:
    ignored = {"the", "and", "for", "with", "that", "this", "use", "let", "our", "are", "was", "about"}
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2 and word not in ignored}
