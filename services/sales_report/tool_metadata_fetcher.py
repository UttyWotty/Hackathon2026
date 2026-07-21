"""
Tool metadata fetcher for sales report generation.
Queries master_shot_table to retrieve approved_ct, commodity (tooling_type),
and cavities for each equipment_code so users do not need to input them manually.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# -- SQL query to fetch tool metadata from master_shot_table --
TOOL_METADATA_QUERY: str = """
    SELECT DISTINCT
        equipment_code,
        tooling_type,
        approved_ct,
        volume AS cavities
    FROM master_shot_table
    WHERE equipment_code IN ({placeholders})
    ORDER BY equipment_code
"""


async def fetch_tool_metadata(
    equipment_codes: List[str],
    client: str = "VANTIS",
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch tool metadata from master_shot_table for given equipment codes.

    Retrieves approved_ct (contracted cycle time), tooling_type (commodity),
    and volume (cavities) per equipment_code.

    Args:
        equipment_codes: List of equipment codes to look up.
        client: Client name for session pool schema selection.

    Returns:
        Dictionary keyed by equipment_code with metadata dicts containing
        approved_ct, commodity, and cavities.
    """
    if not equipment_codes:
        return {}

    try:
        from services.infrastructure.snowflake.session_pool import get_session_pool

        pool = get_session_pool()
        placeholders = ", ".join([f"'{code}'" for code in equipment_codes])
        query = TOOL_METADATA_QUERY.format(placeholders=placeholders)

        results = pool.execute_query(query, client=client)
        metadata: Dict[str, Dict[str, Any]] = {}

        for row in results:
            code = row.get("EQUIPMENT_CODE", row.get("equipment_code", ""))
            metadata[code] = {
                "approved_ct": row.get("APPROVED_CT", row.get("approved_ct")),
                "commodity": row.get(
                    "TOOLING_TYPE", row.get("tooling_type", "Injection")
                ),
                "cavities": row.get("CAVITIES", row.get("cavities")),
            }

        logger.info(
            "Fetched metadata for %d/%d equipment codes",
            len(metadata),
            len(equipment_codes),
        )
        return metadata

    except Exception as exc:
        logger.error("Failed to fetch tool metadata: %s", exc)
        return {}
