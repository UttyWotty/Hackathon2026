"""Searches operator and maintenance shift notes for context on an equipment anomaly.

Runs against the Cortex Search service when a Snowflake connection is configured, and falls
back to a local lexical search over the generated dataset when it is not, so the skill is
usable before an account exists. The two modes are not equivalent and the output says which
one produced the results.

Usage:
    python scripts/search_notes.py EMA-4103
    python scripts/search_notes.py EMA-4103 "cycle time slower cooling"
"""

import csv
import os
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.workflow.note_search import rank_notes  # noqa: E402

SHIFT_NOTE_FILE = "SHIFT_NOTE.csv"
LOCAL_DATA_DIR = os.getenv("LOCAL_DATA_DIR", "")

# Name the Cortex Search service is created under. See the skill's SKILL.md for the DDL.
CORTEX_SEARCH_SERVICE = os.getenv("CORTEX_SEARCH_SERVICE", "shift_note_search")

DEFAULT_LIMIT = int(os.getenv("SHIFT_NOTE_SEARCH_LIMIT", "10"))
SEPARATOR = "-" * 68

EXIT_OK = 0
EXIT_FAILED = 1

MODE_LEXICAL = "local lexical fallback (term overlap, NOT semantic)"
MODE_CORTEX = "Cortex Search (semantic)"


def _load_local_notes() -> List[Dict[str, str]]:
    """Read the generated SHIFT_NOTE rows from disk.

    Raises:
        FileNotFoundError: If LOCAL_DATA_DIR is unset or the file is absent.
    """
    if not LOCAL_DATA_DIR:
        raise FileNotFoundError(
            "No Snowflake connection and LOCAL_DATA_DIR is unset, so there is nothing to "
            "search. Set LOCAL_DATA_DIR to the generator output, for example ./synthetic_out."
        )
    path = Path(LOCAL_DATA_DIR) / SHIFT_NOTE_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Generate it with: "
            f"python -m synthetic_data.generate --output-dir {LOCAL_DATA_DIR}"
        )
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _print_results(mode: str, equipment_code: str, query: str, results: List) -> None:
    """Render the search results, stating which engine produced them."""
    print(SEPARATOR, flush=True)
    print(f"source    : {mode}", flush=True)
    print(f"equipment : {equipment_code or 'all'}", flush=True)
    print(f"query     : {query or '(none - full history in date order)'}", flush=True)
    print(SEPARATOR, flush=True)

    if not results:
        print(
            "No notes matched. This is evidence of absence only if the corpus is",
            flush=True,
        )
        print(
            "complete for this machine and period - say so rather than concluding.",
            flush=True,
        )
        return

    for note in results:
        print(
            f"  {note.shift_date[:10]}  {note.author_role:<12} {note.note_text}",
            flush=True,
        )

    if mode == MODE_LEXICAL:
        print("", flush=True)
        print(
            "NOTE: term-overlap matching only. A paraphrase that shares no words with the "
            "query will be missed here but found by Cortex Search.",
            flush=True,
        )


def main() -> int:
    """Search notes for one equipment code, with an optional free-text query."""
    equipment_code = sys.argv[1] if len(sys.argv) > 1 else ""
    query = sys.argv[2] if len(sys.argv) > 2 else ""

    try:
        notes = _load_local_notes()
    except FileNotFoundError as exc:
        print(f"SEARCH FAILED: {exc}", flush=True)
        return EXIT_FAILED

    results = rank_notes(notes, query, equipment_code or None, DEFAULT_LIMIT)
    _print_results(MODE_LEXICAL, equipment_code, query, results)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
