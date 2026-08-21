"""Reports the period the production dataset actually covers.

The agent reasons about windows like "the last 30 days" relative to today, but
the demo dataset is historical and ends weeks before the current date. Without
this, a mostly-empty window reads to the agent as a collapse in production, and
it reports the dataset ending as though it were a plant event. Fetched once and
cached; every failure degrades to None so a lookup problem cannot break a run.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

COVERAGE_QUERY = """
SELECT MIN(SHOT_TIME) AS FIRST_SHOT,
       MAX(SHOT_TIME) AS LAST_SHOT,
       CURRENT_DATE() AS TODAY
FROM DEMO.PUBLIC.SHOT_DATA
"""


@dataclass(frozen=True)
class DataCoverage:
    """The span of production data available to the agent.

    Attributes:
        first_shot: Date of the earliest shot.
        last_shot: Date of the most recent shot.
        today: The database's current date, used to measure staleness.
    """

    first_shot: date
    last_shot: date
    today: date

    @property
    def days_stale(self) -> int:
        """Days between the most recent shot and today."""
        return (self.today - self.last_shot).days

    @property
    def is_stale(self) -> bool:
        """Whether the newest data predates today by more than a day."""
        return self.days_stale > 1


_cached: Optional[DataCoverage] = None
_looked_up = False


def get_data_coverage() -> Optional[DataCoverage]:
    """Return the dataset's coverage window, or None if it cannot be determined.

    Cached after the first call, including a failed one, so a broken lookup
    costs at most one query per process.

    Returns:
        The coverage window, or None when unavailable.
    """
    global _cached, _looked_up
    if _looked_up:
        return _cached

    _looked_up = True
    try:
        from services.config.features.insights.tools.common import query_records

        rows = query_records(COVERAGE_QUERY)
        if not rows:
            return None
        row = rows[0]
        import pandas as pd

        _cached = DataCoverage(
            first_shot=pd.to_datetime(row["FIRST_SHOT"]).date(),
            last_shot=pd.to_datetime(row["LAST_SHOT"]).date(),
            today=pd.to_datetime(row["TODAY"]).date(),
        )
    except Exception:
        logger.warning("Could not determine data coverage window", exc_info=True)
        _cached = None
    return _cached


def reset_cache() -> None:
    """Clear the cached lookup. For tests."""
    global _cached, _looked_up
    _cached = None
    _looked_up = False
