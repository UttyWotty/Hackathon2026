"""Tests for the pure chart-construction helpers in src/frontend/charts.py.

Covers domain derivation (including the degenerate flat-series case that would
divide by zero) and verifies that each builder compiles to a valid Vega-Lite
spec. No Streamlit runtime and no Snowflake connection are involved.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

import charts  # noqa: E402
import styles  # noqa: E402
import theme  # noqa: E402


class TestPaddedDomain:
    """Tests for charts.padded_domain."""

    def test_pads_both_ends_of_the_range(self):
        low, high = charts.padded_domain(pd.Series([90.0, 95.0, 99.0]))
        assert low < 90.0
        assert high > 99.0

    def test_padding_is_proportional_to_span(self):
        narrow = charts.padded_domain(pd.Series([50.0, 51.0]))
        wide = charts.padded_domain(pd.Series([0.0, 100.0]))
        assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])

    def test_flat_series_does_not_produce_a_zero_width_domain(self):
        low, high = charts.padded_domain(pd.Series([90.0, 90.0]))
        assert high > low

    def test_single_value_series_does_not_produce_a_zero_width_domain(self):
        low, high = charts.padded_domain(pd.Series([42.0]))
        assert high > low

    def test_all_zero_series_does_not_produce_a_zero_width_domain(self):
        low, high = charts.padded_domain(pd.Series([0.0, 0.0]))
        assert high > low

    def test_floor_clamps_the_lower_bound(self):
        low, _ = charts.padded_domain(pd.Series([2.0, 100.0]), floor=0.0)
        assert low == 0.0

    def test_floor_is_ignored_when_data_stays_above_it(self):
        low, _ = charts.padded_domain(pd.Series([50.0, 60.0]), floor=0.0)
        assert low > 0.0

    def test_negative_values_are_handled(self):
        low, high = charts.padded_domain(pd.Series([-20.0, -5.0]))
        assert low < -20.0
        assert high > -5.0


class TestChartBuilders:
    """Tests that the builders compile to valid Vega-Lite specs."""

    def test_status_bar_chart_compiles(self):
        df = pd.DataFrame(
            {
                "PERIOD": pd.to_datetime(["2026-08-01", "2026-08-08"]),
                "AVG_DEVIATION": [1.0, 5.0],
                "SHOTS": [10, 20],
                "STATUS": [theme.SEVERITY_NOMINAL, theme.SEVERITY_WARNING],
            }
        )
        spec = charts.status_bar_chart(
            df,
            x=charts.time_x("PERIOD", "Period"),
            y_field="AVG_DEVIATION",
            y_title="Avg Deviation (s)",
            tooltip=["PERIOD:T", "AVG_DEVIATION", "SHOTS"],
        ).to_dict()
        assert spec["mark"]["type"] == "bar"
        assert spec["encoding"]["color"]["legend"] is None

    def test_status_bar_chart_uses_the_requested_height(self):
        df = pd.DataFrame({"X": [1], "Y": [2], "STATUS": [theme.SEVERITY_NOMINAL]})
        spec = charts.status_bar_chart(
            df,
            x=charts.time_x("X", "X"),
            y_field="Y",
            y_title="Y",
            tooltip=["Y"],
            height=theme.CHART_HEIGHT_STANDARD,
        ).to_dict()
        assert spec["height"] == theme.CHART_HEIGHT_STANDARD

    def test_threshold_rule_compiles_with_rule_and_label(self):
        spec = charts.threshold_rule(10.0, "Warning (10%)", "#F5A524").to_dict()
        marks = [layer["mark"] for layer in spec["layer"]]
        kinds = {m["type"] if isinstance(m, dict) else m for m in marks}
        assert "rule" in kinds
        assert "text" in kinds

    def test_time_x_applies_the_shared_date_format(self):
        assert charts.time_x("W", "Week").to_dict()["axis"]["format"] == (
            theme.DATE_AXIS_FORMAT
        )

    def test_percent_y_without_domain_omits_scale(self):
        assert "scale" not in charts.percent_y("P", "Pct").to_dict()

    def test_percent_y_with_domain_sets_scale(self):
        assert charts.percent_y("P", "Pct", domain=(0, 100)).to_dict()["scale"][
            "domain"
        ] == [0, 100]


class TestThemeVocabulary:
    """Tests that the severity vocabulary and its colour mapping stay aligned."""

    def test_every_severity_level_has_a_colour(self):
        for level in theme.SEVERITY_ORDER:
            assert level in theme.SEVERITY_COLORS

    def test_severity_scale_domain_matches_the_declared_order(self):
        assert theme.severity_scale().domain == theme.SEVERITY_ORDER

    def test_severity_colours_are_distinct(self):
        used = [theme.SEVERITY_COLORS[lvl] for lvl in theme.SEVERITY_ORDER]
        assert len(set(used)) == len(used)

    def test_categorical_palette_has_no_duplicates(self):
        assert len(set(theme.CATEGORICAL_PALETTE)) == len(theme.CATEGORICAL_PALETTE)

    @pytest.mark.parametrize(
        "height",
        [theme.CHART_HEIGHT_HERO, theme.CHART_HEIGHT_STANDARD, theme.CHART_HEIGHT_SPARK],
    )
    def test_chart_heights_are_positive(self, height):
        assert height > 0

    def test_chart_heights_are_ordered(self):
        assert (
            theme.CHART_HEIGHT_HERO
            > theme.CHART_HEIGHT_STANDARD
            > theme.CHART_HEIGHT_SPARK
        )


class TestSeverityBadge:
    """Tests for theme.severity_badge, which replaced the ASCII "!!!" markers."""

    def test_known_severity_renders_a_badge_span(self):
        html = theme.severity_badge(theme.SEVERITY_CRITICAL)
        assert 'class="sev-badge sev-critical"' in html
        assert theme.SEVERITY_CRITICAL in html

    def test_every_severity_level_renders(self):
        for level in theme.SEVERITY_ORDER:
            assert f"sev-{level.lower()}" in theme.severity_badge(level)

    def test_lowercase_input_is_normalised(self):
        assert theme.severity_badge("critical") == theme.severity_badge("CRITICAL")

    def test_surrounding_whitespace_is_tolerated(self):
        assert theme.severity_badge("  WARNING  ") == theme.severity_badge("WARNING")

    def test_unknown_severity_falls_back_to_plain_text(self):
        assert theme.severity_badge("BOGUS") == "BOGUS"

    def test_unknown_severity_emits_no_markup(self):
        assert "<" not in theme.severity_badge("BOGUS")

    def test_stylesheet_defines_a_rule_for_every_level(self):
        for level in theme.SEVERITY_ORDER:
            assert f".sev-{level.lower()}" in styles._STYLESHEET

    def test_stylesheet_uses_each_severity_colour(self):
        for level in theme.SEVERITY_ORDER:
            assert theme.SEVERITY_COLORS[level] in styles._STYLESHEET

    def test_stylesheet_defines_a_banner_rule_for_every_level(self):
        for level in theme.SEVERITY_ORDER:
            assert f".banner-{level.lower()}" in styles._STYLESHEET
