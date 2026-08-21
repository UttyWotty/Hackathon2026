"""The dashboard's stylesheet, built from the design tokens in `theme`.

Streamlit-in-Snowflake ignores `.streamlit/config.toml`, so every visual rule
beyond Altair chart encodings is applied here through a single injected
stylesheet. Kept separate from `theme` so that module stays a pure token
definition with no presentation markup.
"""

import streamlit as st
from theme import (
    ACCENT_PRIMARY,
    RULE_NEUTRAL,
    SEVERITY_COLORS,
    SEVERITY_ORDER,
    SEVERITY_WARNING,
)

_ACCENT_HOVER = "#3D77BC"

_SEVERITY_BADGE_RULES = "".join(
    f"    .sev-badge.sev-{level.lower()} {{ background-color: "
    f"{SEVERITY_COLORS[level]}; }}\n"
    for level in SEVERITY_ORDER
)

_BANNER_RULES = "".join(
    f"    .fleet-banner.banner-{level.lower()} {{ border-left-color: "
    f"{SEVERITY_COLORS[level]}; }}\n"
    f"    .fleet-banner.banner-{level.lower()} strong {{ color: "
    f"{SEVERITY_COLORS[level]}; }}\n"
    for level in SEVERITY_ORDER
)

_STYLESHEET = f"""
<style>
    /* ---- buttons ---- */
    div.stButton > button[kind="primary"] {{
        background-color: {ACCENT_PRIMARY};
        border-color: {ACCENT_PRIMARY};
        color: #FFFFFF;
    }}
    div.stButton > button[kind="primary"]:hover {{
        background-color: {_ACCENT_HOVER};
        border-color: {_ACCENT_HOVER};
        color: #FFFFFF;
    }}
    div.stButton > button[kind="secondary"]:hover {{
        border-color: {ACCENT_PRIMARY};
        color: {ACCENT_PRIMARY};
    }}

    /* ---- severity badges ---- */
    .sev-badge {{
        display: inline-block;
        padding: 1px 9px;
        border-radius: 10px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        color: #FFFFFF;
        vertical-align: middle;
    }}
{_SEVERITY_BADGE_RULES}
    /* ---- page header ---- */
    .app-header {{
        text-align: center;
        padding: 4px 0 14px 0;
    }}
    .app-header .app-eyebrow {{
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        opacity: 0.6;
        margin-bottom: 6px;
    }}
    .app-header .app-title {{
        font-size: 2.05rem;
        font-weight: 700;
        line-height: 1.2;
        letter-spacing: -0.015em;
        margin: 0 0 8px 0;
    }}
    .app-header .app-subtitle {{
        font-size: 0.98rem;
        line-height: 1.6;
        opacity: 0.78;
        max-width: 74ch;
        margin: 0 auto;
    }}

    /* ---- fleet status banner ---- */
    .fleet-banner {{
        border-left: 3px solid {RULE_NEUTRAL};
        padding: 8px 0 8px 14px;
        margin: 4px 0 18px 0;
        font-size: 0.95rem;
        line-height: 1.55;
    }}
{_BANNER_RULES}
    /* ---- ask bar: the agent's front door on the landing screen ---- */
    .ask-bar {{
        border: 1px solid rgba(76, 142, 218, 0.35);
        border-left: 3px solid {ACCENT_PRIMARY};
        border-radius: 8px;
        padding: 12px 16px 6px 16px;
        margin: 6px 0 10px 0;
    }}
    .ask-bar .ask-title {{
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        color: {ACCENT_PRIMARY};
        font-weight: 650;
        margin-bottom: 4px;
    }}
    .ask-bar .ask-sub {{
        font-size: 0.94rem;
        line-height: 1.55;
        opacity: 0.82;
        max-width: 78ch;
    }}
    .ask-answer {{
        border-left: 3px solid {ACCENT_PRIMARY};
        padding: 8px 0 8px 14px;
        margin: 6px 0 12px 0;
    }}
    .ask-answer .ask-answer-q {{
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.6;
        margin-bottom: 4px;
    }}
    .ask-answer .ask-answer-a {{
        font-size: 0.95rem;
        line-height: 1.6;
        max-width: 78ch;
    }}

    /* ---- KPI cards ---- */
    .kpi-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-bottom: 4px;
    }}
    .kpi {{
        flex: 1 1 150px;
        border: 1px solid rgba(128, 138, 153, 0.28);
        border-radius: 8px;
        padding: 12px 14px;
    }}
    .kpi .kpi-label {{
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        opacity: 0.62;
        margin-bottom: 5px;
    }}
    .kpi .kpi-value {{
        font-size: 1.55rem;
        font-weight: 650;
        line-height: 1.15;
        letter-spacing: -0.01em;
    }}
    .kpi .kpi-note {{
        font-size: 0.76rem;
        opacity: 0.62;
        margin-top: 4px;
        line-height: 1.4;
    }}

    /* ---- webhook notification card ---- */
    .wh-card {{
        border: 1px solid rgba(128, 138, 153, 0.30);
        border-left: 3px solid {SEVERITY_COLORS[SEVERITY_WARNING]};
        border-radius: 8px;
        padding: 14px 16px;
        margin: 8px 0;
    }}
    .wh-card .wh-title {{
        font-size: 1.0rem;
        font-weight: 650;
        margin-bottom: 2px;
    }}
    .wh-card .wh-source {{
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        opacity: 0.6;
        margin-bottom: 10px;
    }}
    .wh-card .wh-message {{
        font-size: 0.93rem;
        line-height: 1.6;
        margin-bottom: 12px;
        max-width: 78ch;
    }}
    .wh-card .wh-fields {{
        display: flex;
        flex-wrap: wrap;
        gap: 18px;
    }}
    .wh-card .wh-field {{ min-width: 110px; }}
    .wh-card .wh-flabel {{
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        opacity: 0.55;
    }}
    .wh-card .wh-fvalue {{
        font-size: 0.88rem;
        font-weight: 550;
        margin-top: 1px;
    }}

    /* ---- operator note cards ---- */
    .note-card {{
        border-left: 3px solid {SEVERITY_COLORS[SEVERITY_WARNING]};
        padding: 6px 0 6px 12px;
        margin: 10px 0;
    }}
    .note-card.note-muted {{
        border-left-color: {RULE_NEUTRAL};
        opacity: 0.65;
    }}
    .note-card .note-meta {{
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.65;
        margin-bottom: 2px;
    }}
    .note-card .note-text {{ font-size: 0.95rem; line-height: 1.55; }}
    .note-card .note-match {{
        font-size: 0.78rem;
        opacity: 0.8;
        margin-top: 4px;
        color: {SEVERITY_COLORS[SEVERITY_WARNING]};
    }}

    /* Readable prose inside expanders. Targets a Streamlit internal test id,
       so it degrades to default styling rather than breaking if renamed. */
    [data-testid="stExpanderDetails"] p,
    [data-testid="stExpanderDetails"] li {{
        line-height: 1.65;
        max-width: 78ch;
    }}
    [data-testid="stExpanderDetails"] li {{ margin-bottom: 3px; }}
    [data-testid="stExpanderDetails"] h1,
    [data-testid="stExpanderDetails"] h2,
    [data-testid="stExpanderDetails"] h3 {{
        font-size: 1.02rem;
        font-weight: 600;
        margin-top: 14px;
        margin-bottom: 4px;
    }}
</style>
"""


def inject_css() -> None:
    """Apply the dashboard stylesheet. Call once, early in the app run."""
    st.markdown(_STYLESHEET, unsafe_allow_html=True)
