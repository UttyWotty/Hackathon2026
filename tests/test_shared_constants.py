"""
Tests for shared constants used across analysis modules.

Verifies dataclass values, internal consistency, and mathematical relationships
between TimeConstants, AnalysisThresholds, ShiftBoundaries, and SessionDetection.
These constants govern session detection, shift scheduling, and data quality checks.
"""

from analysis.shared.constants import (
    AnalysisConfig,
    AnalysisThresholds,
    ColumnNames,
    DatabaseSchemas,
    DatabaseTables,
    FilePaths,
    ReportConfig,
    SessionDetection,
    ShiftBoundaries,
    TimeConstants,
)


class TestTimeConstants:
    """Tests for TimeConstants values and mathematical relationships."""

    def test_seconds_per_minute(self) -> None:
        """Seconds per minute is the standard 60."""
        assert TimeConstants.SECONDS_PER_MINUTE == 60

    def test_seconds_per_hour(self) -> None:
        """Seconds per hour equals 60 minutes * 60 seconds."""
        assert TimeConstants.SECONDS_PER_HOUR == 3600

    def test_seconds_per_hour_derived(self) -> None:
        """Seconds per hour is consistent with seconds per minute."""
        expected = TimeConstants.SECONDS_PER_MINUTE * TimeConstants.MINUTES_PER_HOUR
        assert TimeConstants.SECONDS_PER_HOUR == expected

    def test_seconds_per_day(self) -> None:
        """Seconds per day equals 86400."""
        assert TimeConstants.SECONDS_PER_DAY == 86400

    def test_seconds_per_day_derived(self) -> None:
        """Seconds per day is consistent with hours per day."""
        expected = TimeConstants.SECONDS_PER_HOUR * TimeConstants.HOURS_PER_DAY
        assert TimeConstants.SECONDS_PER_DAY == expected

    def test_minutes_per_hour(self) -> None:
        """Minutes per hour is the standard 60."""
        assert TimeConstants.MINUTES_PER_HOUR == 60

    def test_minutes_per_day(self) -> None:
        """Minutes per day equals 1440."""
        assert TimeConstants.MINUTES_PER_DAY == 1440

    def test_minutes_per_day_derived(self) -> None:
        """Minutes per day is consistent with hours per day."""
        expected = TimeConstants.MINUTES_PER_HOUR * TimeConstants.HOURS_PER_DAY
        assert TimeConstants.MINUTES_PER_DAY == expected

    def test_minutes_per_week(self) -> None:
        """Minutes per week equals 10080."""
        assert TimeConstants.MINUTES_PER_WEEK == 10080

    def test_minutes_per_week_derived(self) -> None:
        """Minutes per week is consistent with days per week."""
        expected = TimeConstants.MINUTES_PER_DAY * TimeConstants.DAYS_PER_WEEK
        assert TimeConstants.MINUTES_PER_WEEK == expected

    def test_hours_per_day(self) -> None:
        """Hours per day is the standard 24."""
        assert TimeConstants.HOURS_PER_DAY == 24

    def test_hours_per_week(self) -> None:
        """Hours per week equals 168."""
        assert TimeConstants.HOURS_PER_WEEK == 168

    def test_hours_per_week_derived(self) -> None:
        """Hours per week is consistent with days per week."""
        expected = TimeConstants.HOURS_PER_DAY * TimeConstants.DAYS_PER_WEEK
        assert TimeConstants.HOURS_PER_WEEK == expected

    def test_days_per_week(self) -> None:
        """Days per week is the standard 7."""
        assert TimeConstants.DAYS_PER_WEEK == 7

    def test_days_per_month(self) -> None:
        """Days per month is the 30-day average."""
        assert TimeConstants.DAYS_PER_MONTH == 30

    def test_days_per_year(self) -> None:
        """Days per year is the standard 365."""
        assert TimeConstants.DAYS_PER_YEAR == 365


class TestAnalysisThresholds:
    """Tests for AnalysisThresholds values and ordering."""

    def test_deviation_warning_value(self) -> None:
        """duration deviation warning threshold is 10%."""
        assert AnalysisThresholds.DEVIATION_WARNING == 10.0

    def test_deviation_critical_value(self) -> None:
        """duration deviation critical threshold is 20%."""
        assert AnalysisThresholds.DEVIATION_CRITICAL == 20.0

    def test_deviation_ordering(self) -> None:
        """Warning threshold must be less than critical threshold."""
        assert (
            AnalysisThresholds.DEVIATION_WARNING < AnalysisThresholds.DEVIATION_CRITICAL
        )

    def test_max_acceptable_ct(self) -> None:
        """Max acceptable CT is 999.9 seconds."""
        assert AnalysisThresholds.MAX_ACCEPTABLE_CT == 999.9

    def test_efficiency_excellent(self) -> None:
        """Excellent efficiency is 90%."""
        assert AnalysisThresholds.EFFICIENCY_EXCELLENT == 90.0

    def test_efficiency_good(self) -> None:
        """Good efficiency is 80%."""
        assert AnalysisThresholds.EFFICIENCY_GOOD == 80.0

    def test_efficiency_acceptable(self) -> None:
        """Acceptable efficiency is 70%."""
        assert AnalysisThresholds.EFFICIENCY_ACCEPTABLE == 70.0

    def test_efficiency_poor(self) -> None:
        """Poor efficiency is 60%."""
        assert AnalysisThresholds.EFFICIENCY_POOR == 60.0

    def test_efficiency_ordering(self) -> None:
        """Efficiency thresholds are strictly descending: excellent > good > acceptable > poor."""
        assert (
            AnalysisThresholds.EFFICIENCY_EXCELLENT
            > AnalysisThresholds.EFFICIENCY_GOOD
            > AnalysisThresholds.EFFICIENCY_ACCEPTABLE
            > AnalysisThresholds.EFFICIENCY_POOR
        )

    def test_efficiency_thresholds_are_percentages(self) -> None:
        """All efficiency thresholds are between 0 and 100."""
        for threshold in [
            AnalysisThresholds.EFFICIENCY_EXCELLENT,
            AnalysisThresholds.EFFICIENCY_GOOD,
            AnalysisThresholds.EFFICIENCY_ACCEPTABLE,
            AnalysisThresholds.EFFICIENCY_POOR,
        ]:
            assert 0 < threshold <= 100

    def test_stop_threshold_consistency(self) -> None:
        """Stop threshold in seconds equals stop threshold in minutes * 60."""
        expected = AnalysisThresholds.STOP_THRESHOLD_MINUTES * 60
        assert AnalysisThresholds.STOP_THRESHOLD_SECONDS == expected

    def test_stop_threshold_seconds(self) -> None:
        """Stop threshold is 28800 seconds (8 hours)."""
        assert AnalysisThresholds.STOP_THRESHOLD_SECONDS == 28800

    def test_stop_threshold_minutes(self) -> None:
        """Stop threshold is 480 minutes (8 hours)."""
        assert AnalysisThresholds.STOP_THRESHOLD_MINUTES == 480

    def test_max_null_percentage(self) -> None:
        """Max null percentage is 10%."""
        assert AnalysisThresholds.MAX_NULL_PERCENTAGE == 10.0

    def test_min_data_points(self) -> None:
        """Minimum data points is 10."""
        assert AnalysisThresholds.MIN_DATA_POINTS == 10


class TestShiftBoundaries:
    """Tests for ShiftBoundaries values and shift coverage."""

    def test_day_start_hour(self) -> None:
        """Day shift starts at 06:00."""
        assert ShiftBoundaries.DAY_START_HOUR == 6

    def test_afternoon_start_hour(self) -> None:
        """Afternoon shift starts at 14:00."""
        assert ShiftBoundaries.AFTERNOON_START_HOUR == 14

    def test_night_start_hour(self) -> None:
        """Night shift starts at 22:00."""
        assert ShiftBoundaries.NIGHT_START_HOUR == 22

    def test_shift_ordering(self) -> None:
        """Shift boundaries are in chronological order within a day."""
        assert (
            ShiftBoundaries.DAY_START_HOUR
            < ShiftBoundaries.AFTERNOON_START_HOUR
            < ShiftBoundaries.NIGHT_START_HOUR
        )

    def test_shift_boundaries_within_24_hours(self) -> None:
        """All shift boundaries are valid 24-hour clock values."""
        for hour in [
            ShiftBoundaries.DAY_START_HOUR,
            ShiftBoundaries.AFTERNOON_START_HOUR,
            ShiftBoundaries.NIGHT_START_HOUR,
        ]:
            assert 0 <= hour < 24

    def test_day_shift_duration(self) -> None:
        """Day shift is 8 hours (06:00 to 14:00)."""
        duration = ShiftBoundaries.AFTERNOON_START_HOUR - ShiftBoundaries.DAY_START_HOUR
        assert duration == 8

    def test_afternoon_shift_duration(self) -> None:
        """Afternoon shift is 8 hours (14:00 to 22:00)."""
        duration = (
            ShiftBoundaries.NIGHT_START_HOUR - ShiftBoundaries.AFTERNOON_START_HOUR
        )
        assert duration == 8

    def test_night_shift_duration(self) -> None:
        """Night shift is 8 hours (22:00 to 06:00, wraps around midnight)."""
        duration = (
            24 - ShiftBoundaries.NIGHT_START_HOUR
        ) + ShiftBoundaries.DAY_START_HOUR
        assert duration == 8

    def test_three_shifts_cover_full_day(self) -> None:
        """Three 8-hour shifts cover all 24 hours."""
        day_shift = (
            ShiftBoundaries.AFTERNOON_START_HOUR - ShiftBoundaries.DAY_START_HOUR
        )
        afternoon_shift = (
            ShiftBoundaries.NIGHT_START_HOUR - ShiftBoundaries.AFTERNOON_START_HOUR
        )
        night_shift = (
            24 - ShiftBoundaries.NIGHT_START_HOUR
        ) + ShiftBoundaries.DAY_START_HOUR
        assert day_shift + afternoon_shift + night_shift == 24


class TestSessionDetection:
    """Tests for SessionDetection values and internal consistency."""

    def test_session_gap_hours(self) -> None:
        """Session gap is 8 hours."""
        assert SessionDetection.SESSION_GAP_HOURS == 8

    def test_session_gap_seconds(self) -> None:
        """Session gap in seconds is 28800."""
        assert SessionDetection.SESSION_GAP_SECONDS == 28800

    def test_session_gap_consistency(self) -> None:
        """Session gap seconds equals session gap hours * 3600."""
        expected = SessionDetection.SESSION_GAP_HOURS * TimeConstants.SECONDS_PER_HOUR
        assert SessionDetection.SESSION_GAP_SECONDS == expected

    def test_stop_deviation_threshold(self) -> None:
        """Stop deviation threshold is 5%."""
        assert SessionDetection.STOP_DEVIATION_THRESHOLD == 0.05

    def test_stop_deviation_is_fraction(self) -> None:
        """Stop deviation threshold is between 0 and 1 (a fraction, not a percentage)."""
        assert 0 < SessionDetection.STOP_DEVIATION_THRESHOLD < 1

    def test_gap_time_tolerance_seconds(self) -> None:
        """Gap time tolerance is 2.0 seconds."""
        assert SessionDetection.GAP_TIME_TOLERANCE_SECONDS == 2.0

    def test_gap_time_tolerance_positive(self) -> None:
        """Gap time tolerance must be positive."""
        assert SessionDetection.GAP_TIME_TOLERANCE_SECONDS > 0

    def test_hard_stop_ct(self) -> None:
        """Hard stop CT is 999.9 seconds."""
        assert SessionDetection.HARD_STOP_DURATION == 999.9

    def test_hard_stop_ct_matches_max_acceptable(self) -> None:
        """Hard stop CT aligns with AnalysisThresholds MAX_ACCEPTABLE_duration."""
        assert (
            SessionDetection.HARD_STOP_DURATION == AnalysisThresholds.MAX_ACCEPTABLE_CT
        )

    def test_mode_ct_decimals(self) -> None:
        """Mode CT rounding precision is 2 decimal places."""
        assert SessionDetection.MODE_CT_DECIMALS == 2

    def test_session_gap_matches_stop_threshold(self) -> None:
        """Session gap seconds aligns with AnalysisThresholds stop threshold."""
        assert (
            SessionDetection.SESSION_GAP_SECONDS
            == AnalysisThresholds.STOP_THRESHOLD_SECONDS
        )


class TestAnalysisConfig:
    """Tests for AnalysisConfig default values."""

    def test_default_days_back(self) -> None:
        """Default analysis lookback is 30 days."""
        assert AnalysisConfig.DEFAULT_DAYS_BACK == 30

    def test_max_date_range_days(self) -> None:
        """Maximum date range is 365 days."""
        assert AnalysisConfig.MAX_DATE_RANGE_DAYS == 365

    def test_max_date_range_exceeds_default(self) -> None:
        """Max date range must be greater than default days back."""
        assert AnalysisConfig.MAX_DATE_RANGE_DAYS > AnalysisConfig.DEFAULT_DAYS_BACK

    def test_batch_size_ordering(self) -> None:
        """Batch sizes are in ascending order: small < medium < large."""
        assert (
            AnalysisConfig.BATCH_SIZE_SMALL
            < AnalysisConfig.BATCH_SIZE_MEDIUM
            < AnalysisConfig.BATCH_SIZE_LARGE
        )

    def test_retry_config_values(self) -> None:
        """Retry configuration has sensible defaults."""
        assert AnalysisConfig.MAX_RETRIES == 3
        assert AnalysisConfig.RETRY_DELAY_SECONDS == 2
        assert AnalysisConfig.RETRY_BACKOFF_MULTIPLIER == 2.0

    def test_retry_backoff_multiplier_greater_than_one(self) -> None:
        """Backoff multiplier must be greater than 1 for exponential growth."""
        assert AnalysisConfig.RETRY_BACKOFF_MULTIPLIER > 1.0


class TestFilePaths:
    """Tests for FilePaths directory structure consistency."""

    def test_module_outputs_under_output_dir(self) -> None:
        """All module output directories are under the main output directory."""
        module_outputs = [
            FilePaths.ROI_OUTPUT,
            FilePaths.DEVIATION_OUTPUT,
            FilePaths.EFFICIENCY_OUTPUT,
            FilePaths.RCA_OUTPUT,
            FilePaths.TOOLING_EOL_OUTPUT,
        ]
        for path in module_outputs:
            assert path.startswith(FilePaths.OUTPUT_DIR + "/")

    def test_reports_dir_under_output(self) -> None:
        """Reports directory is under the main output directory."""
        assert FilePaths.REPORTS_DIR.startswith(FilePaths.OUTPUT_DIR + "/")

    def test_file_extensions_have_dot_prefix(self) -> None:
        """All file extensions start with a dot."""
        extensions = [
            FilePaths.EXCEL_EXT,
            FilePaths.CSV_EXT,
            FilePaths.JSON_EXT,
            FilePaths.HTML_EXT,
            FilePaths.PDF_EXT,
        ]
        for ext in extensions:
            assert ext.startswith(".")


class TestDatabaseConstants:
    """Tests for database table and schema constants."""

    def test_table_names_are_uppercase(self) -> None:
        """All table name constants are uppercase (Snowflake convention)."""
        tables = [
            DatabaseTables.SHOT_DATA,
            DatabaseTables.PRODUduration,
            DatabaseTables.ANA_SHOT_MADE,
            DatabaseTables.ROI_TABLE,
            DatabaseTables.EQUIPMENT_MASTER,
        ]
        for table in tables:
            assert table == table.upper()

    def test_schema_names_are_uppercase(self) -> None:
        """All schema name constants are uppercase (Snowflake convention)."""
        schemas = [
            DatabaseSchemas.PUBLIC,
            DatabaseSchemas.NORDPLAST,
            DatabaseSchemas.ANALYTICS,
        ]
        for schema in schemas:
            assert schema == schema.upper()


class TestColumnNames:
    """Tests for column name constants."""

    def test_column_names_are_uppercase(self) -> None:
        """All column name constants are uppercase (Snowflake convention)."""
        columns = [
            ColumnNames.MACHINE_ID,
            ColumnNames.TOOL_ID,
            ColumnNames.SENSOR_CODE,
            ColumnNames.DATE,
            ColumnNames.TIMESTAMP,
            ColumnNames.SHOT_TIME,
            ColumnNames.SHOTS,
            ColumnNames.DURATION,
            ColumnNames.TARGET_DURATION,
            ColumnNames.STATUS,
            ColumnNames.EQUIPMENT_STATUS,
            ColumnNames.PRODUCT_ID,
            ColumnNames.PRODUCT_NAME,
            ColumnNames.VENDOR_NAME,
            ColumnNames.VENDOR_ID,
        ]
        for col in columns:
            assert col == col.upper()

    def test_duration_column_is_ct(self) -> None:
        """Duration column uses the abbreviated CT name."""
        assert ColumnNames.DURATION == "DURATION"


class TestReportConfig:
    """Tests for report generation configuration."""

    def test_chart_dimensions_positive(self) -> None:
        """Chart dimensions must be positive values."""
        assert ReportConfig.CHART_WIDTH > 0
        assert ReportConfig.CHART_HEIGHT > 0
        assert ReportConfig.CHART_DPI > 0

    def test_color_scheme_non_empty(self) -> None:
        """HTML color scheme must contain at least one color."""
        assert len(ReportConfig.HTML_COLOR_SCHEME) > 0

    def test_hex_colors_valid_format(self) -> None:
        """Excel header, highlight, and warning colors are 6-character hex strings."""
        hex_colors = [
            ReportConfig.EXCEL_HEADER_COLOR,
            ReportConfig.EXCEL_HIGHLIGHT_COLOR,
            ReportConfig.EXCEL_WARNING_COLOR,
        ]
        for color in hex_colors:
            assert len(color) == 6
            int(color, 16)  # Raises ValueError if not valid hex
