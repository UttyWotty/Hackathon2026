"""Pure lexical ranking of shift notes, used when Cortex Search is unavailable.

Provides a development fallback so the note-investigation skill can be exercised offline,
and the shaping of results that both paths share. This is deliberately NOT semantic search:
it matches terms, so it will miss a paraphrase that Cortex Search would find. Callers must
label results accordingly rather than presenting them as equivalent.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

# Words too common in shift notes to carry signal, so they are ignored when scoring.
STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "this",
        "that",
        "it",
        "no",
        "not",
        "shift",
        "machine",
        "operator",
        "run",
        "all",
        "any",
        "has",
        "have",
        "had",
    }
)

TOKEN_PATTERN = re.compile(r"[a-z0-9-]+")

# Field names in the SHIFT_NOTE table.
FIELD_EQUIPMENT = "MACHINE_ID"
FIELD_DATE = "SHIFT_DATE"
FIELD_ROLE = "AUTHOR_ROLE"
FIELD_TEXT = "NOTE_TEXT"

DEFAULT_LIMIT = 10


@dataclass
class ScoredNote:
    """One shift note with its lexical relevance score."""

    machine_id: str
    shift_date: str
    author_role: str
    note_text: str
    score: float

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for printing or JSON output."""
        return {
            "machine_id": self.machine_id,
            "shift_date": self.shift_date,
            "author_role": self.author_role,
            "note_text": self.note_text,
            "score": round(self.score, 3),
        }


def tokenize(text: str) -> List[str]:
    """Split text into lowercase content words, dropping stop words.

    Args:
        text: Raw text.

    Returns:
        Content tokens, in order, duplicates preserved.
    """
    return [
        token
        for token in TOKEN_PATTERN.findall((text or "").lower())
        if token not in STOP_WORDS
    ]


def score_note(note_text: str, query_tokens: Sequence[str]) -> float:
    """
    Score one note by the share of query terms it contains.

    Uses coverage of the query rather than raw term counts, so a long note does not
    outrank a short precise one simply by being long.

    Args:
        note_text: The note body.
        query_tokens: Pre-tokenised query terms.

    Returns:
        Fraction of distinct query terms present, 0.0 to 1.0.
    """
    if not query_tokens:
        return 0.0
    note_tokens = set(tokenize(note_text))
    distinct = set(query_tokens)
    hits = sum(1 for token in distinct if token in note_tokens)
    return hits / len(distinct)


def rank_notes(
    notes: List[Dict[str, str]],
    query: str,
    machine_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> List[ScoredNote]:
    """
    Filter and rank notes by lexical relevance to a query.

    Notes scoring zero are dropped: returning every note for the machine would bury the
    signal the caller asked for. When the query is empty every matching note is returned in
    date order, which is the right behaviour for "show me the history".

    Args:
        notes: Raw note rows with SHIFT_NOTE field names.
        query: Free-text query. May be empty.
        machine_id: Restrict to one machine. Defaults to None, meaning all.
        limit: Maximum notes to return. Defaults to 10.

    Returns:
        Notes ranked by score then date, most relevant first.
    """
    query_tokens = tokenize(query)
    selected = [
        note
        for note in notes
        if not machine_id or note.get(FIELD_EQUIPMENT) == machine_id
    ]

    scored = [
        ScoredNote(
            machine_id=note.get(FIELD_EQUIPMENT, ""),
            shift_date=note.get(FIELD_DATE, ""),
            author_role=note.get(FIELD_ROLE, ""),
            note_text=note.get(FIELD_TEXT, ""),
            score=score_note(note.get(FIELD_TEXT, ""), query_tokens),
        )
        for note in selected
    ]

    if query_tokens:
        scored = [note for note in scored if note.score > 0]
        scored.sort(key=lambda note: (-note.score, note.shift_date))
    else:
        scored.sort(key=lambda note: note.shift_date)

    return scored[:limit]
