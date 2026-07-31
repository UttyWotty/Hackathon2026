"""
SQL Builder Module
==================

Generates the complex SQL query for Master Shot Table pipeline.
Includes supplier family mapping and multi-CTE shot-to-part resolution logic.
"""


def get_supplier_family_mapping():
    """Return the supplier-to-tooling-family mapping as a SQL VALUES clause.

    The production system carries a large hardcoded roster of real supplier companies and
    plant locations here; that roster is client-confidential and is not reproduced in this
    repository. The synthetic dataset defines its own suppliers, so this mapping only needs
    to cover them, and any unlisted supplier falls back to 'Unknown' downstream.
    """
    return """
    SELECT COLUMN1 AS supplier_name, COLUMN2 AS tooling_family
    FROM VALUES
        ('NORDPLAST INDUSTRIES', 'Injection Molding'),
        ('ARCWELD COMPONENTS', 'Die Casting'),
        ('MERIDIAN TOOLING', 'Injection Molding')
    """


def build_optimized_shot_query(
    database_name: str, schema_name: str, start_date: str, end_date: str
) -> str:
    """
    Generate optimized shot data query for a specific date range.

    Complex multi-CTE query that:
    - Extracts shot data from DATA_SHOT JSON with date filtering
    - Resolves shot-to-mold assignments from STATISTICS
    - Handles part switching via MOLD_PART with time windows
    - Enriches with supplier/location/timezone data
    - Deduplicates and orders results

    Args:
        database_name: Snowflake database name
        schema_name: Snowflake schema name
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Complete SQL query string
    """

    supplier_family_sql = get_supplier_family_mapping()

    return f"""
WITH 
-- Optimized ShotData CTE with date filtering and improved JSON parsing
ShotData AS (
    SELECT 
        ds.COUNTER_CODE,
        CAST(f.value:ct AS FLOAT) AS ct,
        CAST(f.value:tempMeas AS FLOAT) AS temperature,
        CAST(f.value:seq AS NUMBER) AS seq,
        TO_TIMESTAMP_NTZ(CAST(CAST(f.value:time::STRING AS NUMBER(20,3)) * 1000 AS NUMBER), 3) AS shot_time,
        ds.SHOT_START_TIME,
        ROW_NUMBER() OVER (
            PARTITION BY ds.COUNTER_CODE, ds.SHOT_START_TIME 
            ORDER BY TRY_TO_NUMBER(f.value:time::STRING)
        ) AS shot_sequence
    FROM 
        {database_name}.{schema_name}.DATA_SHOT ds,
        LATERAL FLATTEN(input => TRY_PARSE_JSON(ds.CONTENT)) AS f
    WHERE 
        ds.CONTENT IS NOT NULL  
        AND f.value:ct IS NOT NULL
        AND f.value:time IS NOT NULL
        AND TRY_TO_NUMBER(f.value:time::STRING) IS NOT NULL
        AND TO_DATE(TO_TIMESTAMP(ds.SHOT_START_TIME / 1000000000)) >= '{start_date}'::DATE
        AND TO_DATE(TO_TIMESTAMP(ds.SHOT_START_TIME / 1000000000)) < '{end_date}'::DATE
),

-- Pre-filtered counter assignments
StatsAssignments AS (
    SELECT COUNTER_CODE, MOLD_ID, mold_code, ASSIGNMENT_START
    FROM (
        SELECT
            st.ci AS COUNTER_CODE,
            st.MOLD_ID,
            st.mold_code,
            TRY_TO_TIMESTAMP(TO_VARCHAR(st.HOUR), 'YYYYMMDDHH24') AS ASSIGNMENT_START,
            ROW_NUMBER() OVER (
                PARTITION BY st.ci, TRY_TO_TIMESTAMP(TO_VARCHAR(st.HOUR), 'YYYYMMDDHH24')
                ORDER BY st.HOUR DESC
            ) AS rn
        FROM {database_name}.{schema_name}.STATISTICS st
        WHERE st.HOUR IS NOT NULL 
        AND st.ci IS NOT NULL
        AND st.ci LIKE '%CNT-%'
    ) s
    WHERE ASSIGNMENT_START IS NOT NULL AND rn = 1
),

StatsAssignmentsBounded AS (
    SELECT
        sa.*,
        LEAD(sa.ASSIGNMENT_START) OVER (
            PARTITION BY sa.COUNTER_CODE
            ORDER BY sa.ASSIGNMENT_START
        ) AS ASSIGNMENT_END
    FROM StatsAssignments sa
),

-- Optimized switch processing
CleanSwitches AS (
    SELECT
        mp.MOLD_ID,
        mp.PART_ID,
        mp.CAVITY,
        TO_TIMESTAMP_NTZ(TRY_TO_NUMBER(mp.SWITCHED_TIME)/1000000000) AS SWITCHED_TS
    FROM {database_name}.{schema_name}.MOLD_PART mp
    WHERE mp.SWITCHED_TIME IS NOT NULL
    AND TRY_TO_NUMBER(mp.SWITCHED_TIME) IS NOT NULL
    AND mp.CAVITY > 0
),

SwitchWindows AS (
    SELECT
        MOLD_ID, PART_ID, CAVITY,
        SWITCHED_TS AS START_TS,
        LEAD(SWITCHED_TS) OVER (PARTITION BY MOLD_ID ORDER BY SWITCHED_TS) AS END_TS
    FROM CleanSwitches
),

-- Optimized shot-to-mold resolution
ShotWithMold AS (
    SELECT
        c.name AS supplier_name,
        sd.ct,
        CASE WHEN sd.ct >= 999.9 THEN 'idle' ELSE 'active' END AS ct_status,
        CONVERT_TIMEZONE('UTC', loc.TIME_ZONE_ID, sd.shot_time) AS local_shot_time,
        sd.temperature,
        sd.seq,
        m.contracted_cycle_time / 10.0 AS approved_ct,
        m.tooling_type,
        m.equipment_code,
        m.counter_id,
        stat.COUNTER_CODE AS counter_code,
        m.id AS mold_id,
        c.id AS company_id,
        sd.shot_time
    FROM ShotData sd
    LEFT JOIN StatsAssignmentsBounded stat
        ON sd.COUNTER_CODE = stat.COUNTER_CODE
    AND sd.shot_time >= stat.ASSIGNMENT_START
    AND (sd.shot_time < stat.ASSIGNMENT_END OR stat.ASSIGNMENT_END IS NULL)
    LEFT JOIN {database_name}.{schema_name}.mold m ON stat.MOLD_ID = m.id
    LEFT JOIN {database_name}.{schema_name}.company c ON c.id = m.supplier_company_id
    LEFT JOIN {database_name}.{schema_name}.location loc ON loc.id = m.location_id
    WHERE sd.shot_time IS NOT NULL
),

-- Enhanced part resolution with fallback logic
FallbackCandidates AS (
    SELECT
        swm.mold_id,
        swm.shot_time,
        cs.part_id,
        cs.cavity,
        cs.SWITCHED_TS,
        ROW_NUMBER() OVER (
            PARTITION BY swm.mold_id, swm.shot_time
            ORDER BY cs.SWITCHED_TS DESC, cs.cavity DESC, cs.part_id DESC
        ) AS rn
    FROM ShotWithMold swm
    JOIN CleanSwitches cs
    ON cs.mold_id = swm.mold_id
    AND cs.SWITCHED_TS <= swm.shot_time
    AND cs.cavity > 0
),

PartCandidates AS (
    SELECT
        swm.mold_id,
        swm.shot_time,
        sw.part_id,
        sw.cavity,
        2 AS source_priority
    FROM ShotWithMold swm
    JOIN SwitchWindows sw
      ON sw.mold_id = swm.mold_id
     AND swm.shot_time >= sw.START_TS
     AND (swm.shot_time < sw.END_TS OR sw.END_TS IS NULL)

    UNION ALL

    SELECT
        mold_id,
        shot_time,
        part_id,
        cavity,
        1 AS source_priority
    FROM FallbackCandidates
    WHERE rn = 1
),

SelectedPart AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY mold_id, shot_time ORDER BY source_priority DESC) AS sel_rn
    FROM PartCandidates
),

EnrichedShot AS (
    SELECT
        swm.supplier_name,
        swm.ct,
        swm.ct_status,
        swm.local_shot_time,
        swm.temperature,
        swm.seq,
        CASE 
            WHEN sp.cavity IS NULL OR sp.cavity <= 0 THEN 1
            ELSE sp.cavity 
        END AS volume,
        swm.approved_ct,
        swm.tooling_type,
        swm.equipment_code,
        swm.counter_id,
        swm.counter_code,
        swm.mold_id,
        swm.company_id,
        swm.shot_time AS utc_time_zone,
        p.part_code AS part_id,
        p.name AS part_name
    FROM ShotWithMold swm
    LEFT JOIN SelectedPart sp
    ON sp.mold_id = swm.mold_id AND sp.shot_time = swm.shot_time AND sp.sel_rn = 1
    LEFT JOIN {database_name}.{schema_name}.part p ON p.id = sp.part_id
),

-- Supplier family mapping
SupplierFamily AS (
{supplier_family_sql}
)

SELECT 
    es.supplier_name,
    es.ct,
    es.ct_status,
    es.local_shot_time,
    es.temperature,
    es.volume,
    es.approved_ct,
    es.tooling_type,
    es.equipment_code,
    es.counter_id,
    es.counter_code,
    es.mold_id,
    es.company_id,
    es.part_id,
    es.part_name,
    es.utc_time_zone,
    COALESCE(sf.tooling_family, 'Unknown') AS tooling_family
FROM EnrichedShot es
LEFT JOIN SupplierFamily sf 
    ON es.supplier_name = sf.supplier_name
-- Sequence-based deduplication
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY es.counter_code, es.local_shot_time, es.seq 
    ORDER BY es.part_name DESC NULLS LAST, es.counter_code
) = 1
ORDER BY es.equipment_code, es.local_shot_time
    """
