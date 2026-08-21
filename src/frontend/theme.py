"""Single source of truth for dashboard colour, severity vocabulary, and CSS.

Every chart, badge, and threshold rule in the frontend imports its colours from
this module so the app presents one visual language instead of the three that
accumulated (Bootstrap hexes, ad-hoc accents, and bare CSS colour names).
Streamlit-in-Snowflake ignores `.streamlit/config.toml`, so widget accents are
applied through `inject_css` rather than a theme file.
"""

from typing import Dict, List

import altair as alt

# Canonical severity vocabulary. These strings are also what `classify_severity`
# writes to AUDIT_LOG.SEVERITY, so chart categories and stored data agree.
SEVERITY_CRITICAL: str = "CRITICAL"
SEVERITY_WARNING: str = "WARNING"
SEVERITY_MINOR: str = "MINOR"
SEVERITY_NOMINAL: str = "NOMINAL"

SEVERITY_ORDER: List[str] = [
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    SEVERITY_MINOR,
    SEVERITY_NOMINAL,
]

SEVERITY_COLORS: Dict[str, str] = {
    SEVERITY_CRITICAL: "#E5484D",
    SEVERITY_WARNING: "#F5A524",
    SEVERITY_MINOR: "#4C8EDA",
    SEVERITY_NOMINAL: "#30A46C",
}

# Non-severity accents. Used where a value is a magnitude rather than a
# judgement (Pareto contribution, cumulative lines, min/max bands).
ACCENT_PRIMARY: str = "#4C8EDA"
ACCENT_SECONDARY: str = "#00B8D9"
BAND_FILL: str = "#E5484D"
BAND_OPACITY: float = 0.18

# Reference lines (targets, 100% marks). Mid-grey so they stay legible on both
# the light and dark Snowsight themes, unlike the previous "black" and "green".
RULE_NEUTRAL: str = "#8A94A6"
RULE_DASH: List[int] = [4, 4]

# Categorical palette for series that are identities, not statuses (machine IDs,
# note categories). Ordered for maximum adjacent-hue separation.
CATEGORICAL_PALETTE: List[str] = [
    "#4C8EDA",
    "#E5484D",
    "#30A46C",
    "#F5A524",
    "#9A6DD7",
    "#00B8D9",
    "#E56399",
    "#7A8794",
    "#B5820A",
    "#2F6F5E",
]

# Chart sizing tokens. Three sizes only -- the app previously used seven
# (400, 350, 320, 300, 250, 200, 180), which read as accidental.
CHART_HEIGHT_HERO: int = 360
CHART_HEIGHT_STANDARD: int = 260
CHART_HEIGHT_SPARK: int = 160

# Axis formats. Dates rendered as full timestamps and percentages as raw floats
# before these were applied.
DATE_AXIS_FORMAT: str = "%b %d"
PERCENT_AXIS_FORMAT: str = ".0f"

# Fraction of a value range added as padding when a domain is derived from data
# rather than hardcoded, so points never sit on the axis line.
DOMAIN_PADDING: float = 0.08

def severity_scale() -> alt.Scale:
    """Return the Altair colour scale for the canonical severity vocabulary.

    Returns:
        An `alt.Scale` mapping SEVERITY_ORDER to SEVERITY_COLORS.
    """
    return alt.Scale(
        domain=SEVERITY_ORDER,
        range=[SEVERITY_COLORS[level] for level in SEVERITY_ORDER],
    )


def binary_status_scale() -> alt.Scale:
    """Return a two-value scale for charts that only flag above/below threshold.

    Returns:
        An `alt.Scale` mapping [WARNING, NOMINAL] to their severity colours.
    """
    return alt.Scale(
        domain=[SEVERITY_WARNING, SEVERITY_NOMINAL],
        range=[SEVERITY_COLORS[SEVERITY_WARNING], SEVERITY_COLORS[SEVERITY_NOMINAL]],
    )


def categorical_scale() -> alt.Scale:
    """Return the identity-series colour scale (machine IDs, note categories).

    Returns:
        An `alt.Scale` carrying CATEGORICAL_PALETTE as its range.
    """
    return alt.Scale(range=CATEGORICAL_PALETTE)


def severity_badge(severity: str) -> str:
    """Return an inline HTML badge for a severity value.

    Replaces the ASCII "!!!" / "!!" markers, which read as debug output when
    projected. Callers must render the result with `unsafe_allow_html=True`.

    Args:
        severity: A value from SEVERITY_ORDER.

    Returns:
        An HTML span, or the plain escaped text for an unrecognised severity.
    """
    level = severity.strip().upper()
    if level not in SEVERITY_COLORS:
        return level
    return f'<span class="sev-badge sev-{level.lower()}">{level}</span>'
