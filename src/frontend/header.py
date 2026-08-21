"""Page header and fleet KPI summary for the dashboard.

Renders the first thing an operator sees: what the system is, whether the fleet
needs attention right now, and the five figures that frame everything below.
All values derive from the fleet summary frame already loaded for the Fleet tab,
so this panel costs no additional Snowflake round trip.
"""

import html
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st
from theme import SEVERITY_CRITICAL, SEVERITY_NOMINAL, SEVERITY_WARNING

APP_TITLE = "Autonomous Manufacturing Workflow Agent"
APP_EYEBROW = "Snowflake Cortex | Intelligent Workflow Automation"
APP_SUBTITLE = (
    "Detects gradual duration drift across an injection moulding fleet, "
    "corroborates it against operator shift notes, and raises work orders "
    "and alerts on its own. Built to catch the drift that single-metric "
    "monitors miss, because the machine stays statistically stable while it "
    "degrades."
)

# A machine at or above this deviation from target needs attention. Matches the
# autonomous action threshold in action_loop.
ATTENTION_DEVIATION_PCT = 10.0

# Machines with fewer shots than this are excluded from "worst" rankings: a
# single shot yields a deviation figure with no statistical meaning, and ranking
# on it makes this header contradict the agent's own analysis. Matches
# DEFAULT_MIN_SHOTS in backend analysis/insights/target_validation.py.
MIN_SHOTS_FOR_RANKING = 100

# Deviation at or above which the fleet verdict escalates from warning.
CRITICAL_DEVIATION_PCT = 15.0


def render_header() -> None:
    """Render the centred title block."""
    st.markdown(
        f"""
        <div class="app-header">
            <div class="app-eyebrow">{html.escape(APP_EYEBROW)}</div>
            <div class="app-title">{html.escape(APP_TITLE)}</div>
            <div class="app-subtitle">{html.escape(APP_SUBTITLE)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def rankable(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Return only machines with enough shots to rank meaningfully.

    Falls back to the full frame when nothing clears the bar, so a sparse
    dataset still shows figures rather than nothing.

    Args:
        summary_df: Per-machine fleet summary.

    Returns:
        The subset at or above MIN_SHOTS_FOR_RANKING shots.
    """
    if summary_df.empty or "TOTAL_SHOTS" not in summary_df.columns:
        return summary_df
    eligible = summary_df[summary_df["TOTAL_SHOTS"] >= MIN_SHOTS_FOR_RANKING]
    return summary_df if eligible.empty else eligible


def excluded_count(summary_df: pd.DataFrame) -> int:
    """Count machines held out of rankings for having too few shots."""
    if summary_df.empty:
        return 0
    return len(summary_df) - len(rankable(summary_df))


def _needs_attention(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Return the rankable machines at or above the attention threshold."""
    eligible = rankable(summary_df)
    return eligible[eligible["DEVIATION_PCT"].abs() >= ATTENTION_DEVIATION_PCT]


def build_status_message(summary_df: pd.DataFrame) -> Tuple[str, str]:
    """Compose the fleet verdict and its severity level.

    Reports counts against the assessed subset rather than the whole fleet, and
    states the holdout explicitly: a bare "2 of 9" alongside a "10 machines"
    KPI reads as an inconsistency with no explanation.

    Args:
        summary_df: Per-machine fleet summary.

    Returns:
        A (severity_level, html_message) pair.
    """
    flagged = _needs_attention(summary_df)
    assessed = len(rankable(summary_df))
    excluded = excluded_count(summary_df)
    total = len(summary_df)

    if flagged.empty:
        level = SEVERITY_NOMINAL
        message = (
            f"<strong>Fleet nominal.</strong> All {assessed} assessed machines "
            f"are within {ATTENTION_DEVIATION_PCT:.0f}% of target duration."
        )
    else:
        worst = flagged.loc[flagged["DEVIATION_PCT"].abs().idxmax()]
        level = (
            SEVERITY_CRITICAL
            if abs(worst["DEVIATION_PCT"]) >= CRITICAL_DEVIATION_PCT
            else SEVERITY_WARNING
        )
        machine = html.escape(str(worst["MACHINE_ID"]))
        message = (
            f"<strong>{len(flagged)} of {assessed} assessed machines need "
            f"attention.</strong> Worst is {machine} at "
            f"{worst['DEVIATION_PCT']:.1f}% above target."
        )

    if excluded:
        message += (
            f'<span class="banner-note">Assessed {assessed} of {total} '
            f"machines. {excluded} held out with fewer than "
            f"{MIN_SHOTS_FOR_RANKING} shots recorded, too little data to rank "
            "fairly.</span>"
        )
    return level, message


def render_fleet_status(summary_df: pd.DataFrame) -> None:
    """Render a one-line verdict on whether the fleet needs attention.

    Args:
        summary_df: Per-machine fleet summary.
    """
    if summary_df.empty:
        return
    level, message = build_status_message(summary_df)
    st.markdown(
        f'<div class="fleet-banner banner-{level.lower()}">{message}</div>',
        unsafe_allow_html=True,
    )


def _kpi(label: str, value: str, note: Optional[str] = None) -> str:
    """Build the HTML for one KPI card."""
    note_html = (
        f'<div class="kpi-note">{html.escape(note)}</div>' if note else ""
    )
    return (
        '<div class="kpi">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-value">{html.escape(value)}</div>'
        f"{note_html}</div>"
    )


def _latest_reading(summary_df: pd.DataFrame) -> Optional[pd.Timestamp]:
    """Return the most recent shot timestamp across the fleet, if present."""
    if "LAST_SHOT" not in summary_df.columns:
        return None
    latest = pd.to_datetime(summary_df["LAST_SHOT"], errors="coerce").max()
    return None if pd.isna(latest) else latest


def build_kpis(summary_df: pd.DataFrame) -> List[Tuple[str, str, Optional[str]]]:
    """Compute the KPI cards as (label, value, note) triples.

    Pure: takes a frame and returns text, so the figures can be asserted on
    without a Streamlit runtime.

    Args:
        summary_df: Per-machine fleet summary.

    Returns:
        A list of (label, value, note) triples in display order.
    """
    if summary_df.empty:
        return []

    total_shots = int(summary_df["TOTAL_SHOTS"].sum())
    machines = len(summary_df)
    flagged = len(_needs_attention(summary_df))

    eligible = rankable(summary_df)

    worst_idx = eligible["DEVIATION_PCT"].abs().idxmax()
    worst_dev = eligible.loc[worst_idx, "DEVIATION_PCT"]
    worst_machine = str(eligible.loc[worst_idx, "MACHINE_ID"])

    stability = 100.0 - eligible["CV_PCT"]
    weakest_idx = stability.idxmin()
    weakest = stability.loc[weakest_idx]
    weakest_machine = str(eligible.loc[weakest_idx, "MACHINE_ID"])

    attention_note = (
        f"at or above {ATTENTION_DEVIATION_PCT:.0f}% deviation from target, "
        f"of {len(eligible)} assessed machines"
    )

    latest = _latest_reading(summary_df)

    return [
        (
            "Fleet",
            f"{machines} machines",
            f"{total_shots:,} shots analysed",
        ),
        ("Needs Attention", str(flagged), attention_note),
        (
            "Worst Deviation",
            f"{worst_dev:.1f}%",
            f"{worst_machine} — longest cycle time vs target",
        ),
        (
            "Lowest Stability",
            f"{weakest:.1f}%",
            f"{weakest_machine} — most shot-to-shot variation",
        ),
        (
            "Latest Reading",
            latest.strftime("%d %b %Y") if latest is not None else "unknown",
            "most recent telemetry received",
        ),
    ]


def render_kpi_cards(summary_df: pd.DataFrame) -> None:
    """Render the fleet KPI row.

    Args:
        summary_df: Per-machine fleet summary.
    """
    kpis = build_kpis(summary_df)
    if not kpis:
        st.info("No fleet data available yet.")
        return
    cards = "".join(_kpi(label, value, note) for label, value, note in kpis)
    st.markdown(f'<div class="kpi-row">{cards}</div>', unsafe_allow_html=True)
