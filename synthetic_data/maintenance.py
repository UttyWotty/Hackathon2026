"""Pure generation of completed maintenance work orders for the synthetic dataset.

Produces WORK_ORDER rows spaced at per-archetype intervals so tooling_eol's maintenance
interval and remaining-life logic has non-empty, differentiated input. Contains no I/O and
derives all timestamps from the injected generation window rather than the clock.
"""

from datetime import datetime, timedelta
from typing import Dict, Final, List

from .constants import WORK_ORDER_ID_BASE, WORK_ORDER_STATUS_COMPLETED
from .models import EquipmentProfile, GenerationConfig, ProfileKind, WorkOrder

ORDER_TYPE_PREVENTIVE: Final[str] = "PREVENTIVE"
ORDER_TYPE_CORRECTIVE: Final[str] = "CORRECTIVE"

# Days between completed maintenance events, per archetype. Equipment with planted stop
# defects are serviced more often, which is the pattern tooling_eol should surface.
MAINTENANCE_INTERVAL_DAYS: Final[Dict[ProfileKind, int]] = {
    ProfileKind.STABLE: 21,
    ProfileKind.CT_DRIFT: 21,
    ProfileKind.FREQUENT_STOPS: 7,
    ProfileKind.LONG_REPAIRS: 10,
    ProfileKind.DECLINING: 14,
}

# Archetypes whose maintenance is reactive rather than scheduled.
CORRECTIVE_KINDS: Final[frozenset] = frozenset(
    {ProfileKind.FREQUENT_STOPS, ProfileKind.LONG_REPAIRS, ProfileKind.DECLINING}
)

# Hour of day at which a maintenance event is recorded complete.
COMPLETION_HOUR: Final[int] = 17


def _completion_times(config: GenerationConfig, interval_days: int) -> List[datetime]:
    """Return every maintenance completion timestamp inside the dataset window."""
    window_days = config.weeks * 7
    return [
        config.window_start + timedelta(days=day_offset, hours=COMPLETION_HOUR)
        for day_offset in range(interval_days, window_days, interval_days)
    ]


def build_work_orders(
    profiles: List[EquipmentProfile], config: GenerationConfig
) -> List[WorkOrder]:
    """Build the completed WORK_ORDER rows for every equipment in the roster."""
    work_orders: List[WorkOrder] = []
    next_id = WORK_ORDER_ID_BASE
    for profile in profiles:
        interval_days = MAINTENANCE_INTERVAL_DAYS[profile.kind]
        order_type = (
            ORDER_TYPE_CORRECTIVE
            if profile.kind in CORRECTIVE_KINDS
            else ORDER_TYPE_PREVENTIVE
        )
        for completed_at in _completion_times(config, interval_days):
            work_orders.append(
                WorkOrder(
                    id=next_id,
                    tool_id=profile.mold.id,
                    status=WORK_ORDER_STATUS_COMPLETED,
                    completed_at=completed_at,
                    order_type=order_type,
                )
            )
            next_id += 1
    return work_orders
