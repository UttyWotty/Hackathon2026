"""Shared fixtures and helpers for the synthetic data generator test suite.

Provides the dimension-lookup context that shot generation requires without duplicating the
assembly logic in every test module. Contains no I/O and no Snowflake access.
"""

from typing import List

from synthetic_data.dimensions import (
    build_companies,
    build_locations,
    part_code_by_id,
    part_name_by_code,
)
from synthetic_data.models import Part, ShotContext


def build_context(parts: List[Part]) -> ShotContext:
    """Assemble the denormalisation lookups used when constructing shot rows."""
    companies = build_companies()
    locations = build_locations()
    return ShotContext(
        supplier_name_by_company_id={company.id: company.name for company in companies},
        location_by_id={location.id: location for location in locations},
        part_code_by_id=part_code_by_id(parts),
        part_name_by_code=part_name_by_code(parts),
    )
