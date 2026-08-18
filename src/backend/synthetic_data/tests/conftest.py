"""Shared fixtures and helpers for the synthetic data generator test suite.

Provides the dimension-lookup context that shot generation requires without duplicating the
assembly logic in every test module. Contains no I/O and no Snowflake access.
"""

from typing import List

from synthetic_data.dimensions import (
    build_companies,
    build_locations,
    product_code_by_id,
    product_name_by_code,
)
from synthetic_data.models import Part, ShotContext


def build_context(parts: List[Part]) -> ShotContext:
    """Assemble the denormalisation lookups used when constructing shot rows."""
    companies = build_companies()
    locations = build_locations()
    return ShotContext(
        vendor_name_by_vendor_id={company.id: company.name for company in companies},
        location_by_id={location.id: location for location in locations},
        product_code_by_id=product_code_by_id(parts),
        product_name_by_code=product_name_by_code(parts),
    )
