"""Serialization of synthetic dataclasses into positional rows matching the table DDL.

Each function returns values in exactly the column order declared in ddl.TABLE_COLUMNS, so
CSV headers and INSERT column lists stay in lockstep with the data. This module is pure and
performs no formatting decisions beyond ISO-8601 timestamps.
"""

from datetime import datetime
from typing import Any, List, Sequence

from .models import Company, Location, Mold, Part, ShiftNote, Shot, WorkOrder

# Snowflake parses this format directly into TIMESTAMP_NTZ with millisecond precision.
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def format_timestamp(value: datetime) -> str:
    """Render a naive datetime in the millisecond-precision format Snowflake expects."""
    return value.strftime(TIMESTAMP_FORMAT)[:-3]


def shot_row(shot: Shot) -> Sequence[Any]:
    """Serialize one shot into SHOT_DATA column order.

    intended_stop_kind is deliberately omitted: it is generator metadata, not a table column.
    """
    return (
        shot.vendor_name,
        shot.machine_id,
        shot.sensor_code,
        shot.ct,
        shot.target_duration,
        shot.temperature,
        shot.product_name,
        shot.process_type,
        shot.type_category,
        shot.status_flag,
        format_timestamp(shot.shot_time),
        format_timestamp(shot.shot_time_utc),
        shot.volume,
        shot.sensor_id,
        shot.tool_id,
        shot.vendor_id,
        shot.product_id,
        format_timestamp(shot.upload_time),
        shot.processing_date,
    )


def mold_row(mold: Mold) -> Sequence[Any]:
    """Serialize one mold into MOLD column order."""
    return (
        mold.id,
        mold.machine_id,
        mold.sensor_code,
        mold.sensor_id,
        mold.vendor_vendor_id,
        mold.location_id,
        mold.product_id,
        mold.process_type,
        mold.target_duration,
        mold.total_cavities,
        mold.designed_shot,
        mold.max_daily_output,
        mold.production_days,
        mold.shifts_per_day,
    )


def vendor_row(company: Company) -> Sequence[Any]:
    """Serialize one company into COMPANY column order."""
    return (company.id, company.name)


def location_row(location: Location) -> Sequence[Any]:
    """Serialize one location into LOCATION column order."""
    return (
        location.id,
        location.name,
        location.tz_code,
        location.utc_offset_hours,
    )


def product_row(part: Part) -> Sequence[Any]:
    """Serialize one part into PART column order."""
    return (part.id, part.product_code, part.name)


def work_order_row(work_order: WorkOrder) -> Sequence[Any]:
    """Serialize one work order into WORK_ORDER column order."""
    return (
        work_order.id,
        work_order.tool_id,
        work_order.status,
        format_timestamp(work_order.completed_at),
        work_order.order_type,
    )


def shift_note_row(note: ShiftNote) -> Sequence[Any]:
    """Serialize one shift note into SHIFT_NOTE column order.

    mentions_symptom is intentionally omitted: it is generator ground truth, not data the
    agent is allowed to see.
    """
    return (
        note.id,
        note.machine_id,
        format_timestamp(note.shift_date),
        note.author_role,
        note.note_text,
    )


def shot_rows(shots: List[Shot]) -> List[Sequence[Any]]:
    """Serialize a shot list, preserving order."""
    return [shot_row(shot) for shot in shots]
