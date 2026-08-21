"""Correlation of operator shift notes with quantitative duration drift.

Scans free-text notes for wear-related language and matches each hit to the
nearest weekly deviation figure, which is the evidence that the numeric anomaly
and the operators' own observations describe the same failure. The matching
rules are pure functions; only `render_corroboration_panel` touches Streamlit.
"""

import html
from typing import List, Optional, Sequence, Tuple

import pandas as pd
import streamlit as st

# Language operators use for progressive tooling wear. Matched case-insensitively
# as substrings, so "cooling" also catches "cooling channel".
CORROBORATION_KEYWORDS: Tuple[str, ...] = (
    "drift",
    "creep",
    "slow",
    "over standard",
    "compensation",
    "sluggish",
    "cooling",
    "ejection",
    "drag",
    "recommend pulling",
    "significantly long",
    "well over",
)


def is_corroborating(note_text: object) -> bool:
    """Report whether a note contains wear-related language.

    Args:
        note_text: The note body; non-string values are coerced.

    Returns:
        True when any corroboration keyword appears in the note.
    """
    if note_text is None:
        return False
    lowered = str(note_text).lower()
    return any(keyword in lowered for keyword in CORROBORATION_KEYWORDS)


def nearest_week_index(
    note_date: pd.Timestamp, week_starts: Sequence[pd.Timestamp]
) -> Optional[int]:
    """Find the index of the week closest to a note's date.

    Args:
        note_date: Date the note was written.
        week_starts: Week-start timestamps, in any order.

    Returns:
        The index of the nearest week, or None when there are no weeks.
    """
    weeks = pd.to_datetime(pd.Series(list(week_starts)))
    if weeks.empty:
        return None
    return int((weeks - pd.to_datetime(note_date)).abs().argmin())


def _note_card(meta: str, body: str, match: Optional[str], muted: bool) -> str:
    """Build the HTML for one note card.

    Note bodies come from the database, so every interpolated value is escaped.

    Args:
        meta: Small-caps header line (date and author role).
        body: The note text.
        match: Optional correlation line, rendered in the warning colour.
        muted: Render de-emphasised, for notes with no wear language.

    Returns:
        An HTML string for `st.markdown(..., unsafe_allow_html=True)`.
    """
    classes = "note-card note-muted" if muted else "note-card"
    parts = [
        f'<div class="{classes}">',
        f'<div class="note-meta">{html.escape(meta)}</div>',
        f'<div class="note-text">{html.escape(body)}</div>',
    ]
    if match:
        parts.append(f'<div class="note-match">{html.escape(match)}</div>')
    parts.append("</div>")
    return "".join(parts)


def _format_meta(note_row: pd.Series) -> str:
    """Build the header line for a note card."""
    shift_date = pd.to_datetime(note_row["SHIFT_DATE"]).strftime("%d %b %Y")
    return f"{shift_date}  ·  {note_row['AUTHOR_ROLE']}"


def render_corroboration_panel(
    notes: pd.DataFrame, drift_detail: pd.DataFrame, equipment: str
) -> None:
    """Render operator notes, highlighting those that corroborate the drift.

    Safe to call from inside an expander: this function creates no expander of
    its own, since Streamlit does not allow them to nest.

    Args:
        notes: SHIFT_DATE, AUTHOR_ROLE, NOTE_TEXT for one machine.
        drift_detail: Weekly WEEK_START and DEVIATION_PCT for the same machine.
        equipment: Machine identifier, used in the summary line and widget key.
    """
    if notes.empty or drift_detail.empty:
        st.info("No operator notes recorded for this machine.")
        return

    week_starts = pd.to_datetime(drift_detail["WEEK_START"])
    deviations = drift_detail["DEVIATION_PCT"].tolist()

    matched: List[str] = []
    others: List[str] = []

    for _, note_row in notes.iterrows():
        body = str(note_row["NOTE_TEXT"])
        meta = _format_meta(note_row)
        if not is_corroborating(body):
            others.append(_note_card(meta, body, None, muted=True))
            continue
        index = nearest_week_index(note_row["SHIFT_DATE"], week_starts)
        match = None
        if index is not None:
            match = (
                f"Corroborates {deviations[index]:.1f}% deviation, "
                f"week of {week_starts.iloc[index].strftime('%d %b %Y')}"
            )
        matched.append(_note_card(meta, body, match, muted=False))

    st.caption(
        f"{len(matched)} of {len(notes)} operator notes for {equipment} use "
        "wear-related language. Each is matched to the nearest weekly deviation."
    )

    if matched:
        st.markdown("**Notes corroborating the drift**")
        st.markdown("".join(matched), unsafe_allow_html=True)

    if others:
        # A checkbox rather than an expander: this panel already renders inside
        # one, and Streamlit does not allow expanders to nest.
        if st.checkbox(
            f"Show {len(others)} other note(s)",
            key=f"show_other_notes_{equipment}",
            value=False,
        ):
            st.markdown("".join(others), unsafe_allow_html=True)
