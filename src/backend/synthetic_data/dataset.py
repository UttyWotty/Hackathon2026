"""Assembly of a complete synthetic dataset from a generation config.

Composes the dimension builders, shot generator, maintenance generator and ground-truth
declaration into one reproducible result keyed by table name. Pure: it returns serialized
rows and expectations, and never writes files or opens connections.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from .constants import (
    TABLE_LOCATION,
    TABLE_MASTER_SHOT,
    TABLE_PRODUCT,
    TABLE_SHIFT_NOTE,
    TABLE_TOOL,
    TABLE_VENDOR,
    TABLE_WORK_ORDER,
)
from .dimensions import (
    build_companies,
    build_locations,
    build_molds,
    build_parts,
    build_profiles,
    product_code_by_id,
    product_name_by_code,
)
from .ground_truth import build_expected_findings, demo_headline_equipment
from .maintenance import build_work_orders
from .models import (
    EquipmentProfile,
    ExpectedFinding,
    GenerationConfig,
    ShiftNote,
    Shot,
    ShotContext,
)
from .notes import build_shift_notes
from .rows import (
    location_row,
    mold_row,
    product_row,
    shift_note_row,
    shot_rows,
    vendor_row,
    work_order_row,
)
from .shots import generate_all_shots


@dataclass(frozen=True)
class Dataset:
    """A generated dataset: serialized rows per table plus its verification contract.

    tables maps table name to DDL-ordered rows ready for CSV or COPY INTO. shots retains the
    rich Shot objects so tests and summaries can inspect intended stop kinds.
    """

    tables: Dict[str, List[Sequence[Any]]]
    shots: List[Shot]
    shift_notes: List[ShiftNote]
    profiles: List[EquipmentProfile]
    expected_findings: List[ExpectedFinding]
    headline_equipment: str


def build_dataset(config: GenerationConfig) -> Dataset:
    """Generate every table for one dataset window from a single seeded config."""
    companies = build_companies()
    locations = build_locations()
    parts = build_parts()
    molds = build_molds(parts, config.production_days_per_week, config.shift_hours)
    profiles = build_profiles(molds)

    context = ShotContext(
        vendor_name_by_vendor_id={company.id: company.name for company in companies},
        location_by_id={location.id: location for location in locations},
        product_code_by_id=product_code_by_id(parts),
        product_name_by_code=product_name_by_code(parts),
    )

    shots = generate_all_shots(profiles, context, config)
    work_orders = build_work_orders(profiles, config)
    shift_notes = build_shift_notes(profiles, config)

    tables: Dict[str, List[Sequence[Any]]] = {
        TABLE_VENDOR: [vendor_row(company) for company in companies],
        TABLE_LOCATION: [location_row(location) for location in locations],
        TABLE_PRODUCT: [product_row(part) for part in parts],
        TABLE_TOOL: [mold_row(mold) for mold in molds],
        TABLE_WORK_ORDER: [work_order_row(work_order) for work_order in work_orders],
        TABLE_MASTER_SHOT: shot_rows(shots),
        TABLE_SHIFT_NOTE: [shift_note_row(note) for note in shift_notes],
    }

    return Dataset(
        tables=tables,
        shots=shots,
        shift_notes=shift_notes,
        profiles=profiles,
        expected_findings=build_expected_findings(profiles),
        headline_equipment=demo_headline_equipment(profiles),
    )


def summarize(dataset: Dataset) -> Dict[str, int]:
    """Return per-table row counts, used for the generator's console summary."""
    return {table: len(rows) for table, rows in dataset.tables.items()}
