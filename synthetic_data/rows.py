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
    """Serialize one shot into DEMO_TABLE column order.

    intended_stop_kind is deliberately omitted: it is generator metadata, not a table column.
    """
    return (
        shot.supplier_name,
        shot.equipment_code,
        shot.counter_code,
        shot.ct,
        shot.approved_ct,
        shot.temperature,
        shot.part_name,
        shot.tooling_type,
        shot.tooling_family,
        shot.ct_status,
        format_timestamp(shot.local_shot_time),
        format_timestamp(shot.utc_time_zone),
        shot.volume,
        shot.counter_id,
        shot.mold_id,
        shot.company_id,
        shot.part_id,
        format_timestamp(shot.upload_time),
        shot.processing_date,
    )


def mold_row(mold: Mold) -> Sequence[Any]:
    """Serialize one mold into MOLD column order."""
    return (
        mold.id,
        mold.equipment_code,
        mold.counter_code,
        mold.counter_id,
        mold.supplier_company_id,
        mold.location_id,
        mold.part_id,
        mold.tooling_type,
        mold.contracted_cycle_time,
        mold.total_cavities,
        mold.designed_shot,
        mold.daily_max_capacity,
        mold.production_days,
        mold.shifts_per_day,
    )


def company_row(company: Company) -> Sequence[Any]:
    """Serialize one company into COMPANY column order."""
    return (company.id, company.name)


def location_row(location: Location) -> Sequence[Any]:
    """Serialize one location into LOCATION column order."""
    return (
        location.id,
        location.name,
        location.time_zone_id,
        location.utc_offset_hours,
    )


def part_row(part: Part) -> Sequence[Any]:
    """Serialize one part into PART column order."""
    return (part.id, part.part_code, part.name)


def work_order_row(work_order: WorkOrder) -> Sequence[Any]:
    """Serialize one work order into WORK_ORDER column order."""
    return (
        work_order.id,
        work_order.mold_id,
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
        note.equipment_code,
        format_timestamp(note.shift_date),
        note.author_role,
        note.note_text,
    )


def shot_rows(shots: List[Shot]) -> List[Sequence[Any]]:
    """Serialize a shot list, preserving order."""
    return [shot_row(shot) for shot in shots]
