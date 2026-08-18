"""
Recommendation generation for Pareto-based root cause analysis.
Provides a function to generate prioritised actionable recommendations from
pre-computed process-duration, downtime, and scrap analysis results.
Separated from the analysis module to keep each file under the 500-line limit.
"""

from typing import Dict, List

import pandas as pd

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_recommendations(df: pd.DataFrame) -> None:
    """Generate and print prioritised actionable recommendations.

    Args:
        df: DataFrame with CT_ISSUE_FLAG, DOWNTIME_EVENT, SCRAP_INDICATOR,
            and related columns already computed.
    """
    print("\n" + "=" * 60)
    print("  ACTIONABLE RECOMMENDATIONS")
    print("=" * 60)

    recommendations: List[Dict[str, str]] = []

    ct_issues = df[df["CT_ISSUE_FLAG"]]
    downtime_issues = df[df["DOWNTIME_EVENT"]]
    scrap_issues = df[df["SCRAP_INDICATOR"]]

    _add_ct_recommendations(ct_issues, recommendations)
    _add_downtime_recommendations(df, downtime_issues, recommendations)
    _add_scrap_recommendations(df, scrap_issues, recommendations)

    if recommendations:
        rec_df = pd.DataFrame(recommendations)
        print("\n  Prioritized Action Items:")
        for i, rec in rec_df.iterrows():
            print("\n%d. %s - %s" % (i + 1, rec["Category"], rec["Issue"]))
            print("   Action: %s" % rec["Action"])
            print("   Impact: %s" % rec["Impact"])
            print("   Priority: %s" % rec["Priority"])
    else:
        print(
            "  No significant issues identified -- current processes "
            "are performing well."
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _add_ct_recommendations(
    ct_issues: pd.DataFrame,
    recommendations: List[Dict[str, str]],
) -> None:
    """Append process-duration recommendations to the list."""
    if len(ct_issues) == 0:
        return

    top_equip = ct_issues["MACHINE_ID"].value_counts().head(3)
    for equipment, count in top_equip.items():
        recommendations.append(
            {
                "Priority": "High",
                "Category": "Equipment",
                "Issue": "Equipment %s has %d duration issues" % (equipment, count),
                "Action": "Perform preventive maintenance on %s" % equipment,
                "Impact": "Addresses %.1f%% of all CT issues"
                % (count / len(ct_issues) * 100),
            }
        )

    top_parts = ct_issues["PRODUCT_NAME"].value_counts().head(3)
    for part, count in top_parts.items():
        recommendations.append(
            {
                "Priority": "Medium",
                "Category": "Part",
                "Issue": "Part %s has %d duration issues" % (part, count),
                "Action": "Review process parameters for %s" % part,
                "Impact": "Addresses %.1f%% of all CT issues"
                % (count / len(ct_issues) * 100),
            }
        )


def _add_downtime_recommendations(
    df: pd.DataFrame,
    downtime_issues: pd.DataFrame,
    recommendations: List[Dict[str, str]],
) -> None:
    """Append downtime recommendations to the list."""
    if len(downtime_issues) == 0:
        return

    top_parts = downtime_issues["PRODUCT_NAME"].value_counts().head(3)
    for part, count in top_parts.items():
        recommendations.append(
            {
                "Priority": "High",
                "Category": "Downtime",
                "Issue": "Part %s has %d downtime events" % (part, count),
                "Action": "Investigate setup and changeover procedures for %s" % part,
                "Impact": "Addresses %.1f%% of all downtime events"
                % (count / len(downtime_issues) * 100),
            }
        )

    longest_gaps = df[df["TIME_GAP_MINUTES"] > 0].nlargest(1, "TIME_GAP_MINUTES")
    if len(longest_gaps) > 0:
        longest = longest_gaps.iloc[0]
        recommendations.append(
            {
                "Priority": "Critical",
                "Category": "Downtime",
                "Issue": "Longest downtime: %.1f minutes" % longest["TIME_GAP_MINUTES"],
                "Action": "Review what happened on %s with part %s"
                % (longest["SHOT_TIME"], longest["PRODUCT_NAME"]),
                "Impact": "Addresses longest single downtime event",
            }
        )


def _add_scrap_recommendations(
    df: pd.DataFrame,
    scrap_issues: pd.DataFrame,
    recommendations: List[Dict[str, str]],
) -> None:
    """Append scrap recommendations to the list."""
    if len(scrap_issues) == 0:
        return

    top_parts = scrap_issues["PRODUCT_NAME"].value_counts().head(3)
    for part, count in top_parts.items():
        recommendations.append(
            {
                "Priority": "High",
                "Category": "Scrap",
                "Issue": "Part %s has %d suspected scrap shots" % (part, count),
                "Action": "Review process parameters and quality checks for %s" % part,
                "Impact": "Addresses %.1f%% of all scrap issues"
                % (count / len(scrap_issues) * 100),
            }
        )

    highest = df[df["SCRAP_SCORE"] >= 3].nlargest(1, "SCRAP_SCORE")
    if len(highest) > 0:
        worst = highest.iloc[0]
        recommendations.append(
            {
                "Priority": "Critical",
                "Category": "Scrap",
                "Issue": "Shot with highest scrap score (%d)" % worst["SCRAP_SCORE"],
                "Action": "Investigate %s - %s (CT: %.1fs)"
                % (worst["SHOT_TIME"], worst["PRODUCT_NAME"], worst["DURATION"]),
                "Impact": "Addresses most problematic production shot",
            }
        )

    warmup = df[df["SCRAP_WARMUP"]]
    if len(warmup) > 0:
        recommendations.append(
            {
                "Priority": "Medium",
                "Category": "Scrap",
                "Issue": "%d warm-up shots detected after idle periods" % len(warmup),
                "Action": "Review warm-up procedures and consider scrapping first few shots",
                "Impact": "Addresses %.1f%% of scrap issues"
                % (len(warmup) / len(scrap_issues) * 100),
            }
        )
