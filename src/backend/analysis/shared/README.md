# Shared Utilities Package

**Version:** 1.0.0  
**Author:** Utku Gulbardak  
**Date:** 2025-10-28

## Overview

The `analysis/shared/` package provides centralized utilities for all manufacturing analysis modules. This eliminates code duplication and ensures consistent behavior across all analysis tools.

## 📦 Package Contents

### 1. **connections.py** - Snowflake Connection Management
Handles all database connection operations with retry logic and authentication.

**Key Functions:**
- `create_snowflake_connection()` - Create connection with retry logic
- `get_snowflake_connection_params()` - Get connection parameters
- `load_private_key()` - Load P8 private key for authentication
- `test_snowflake_connection()` - Health check

**Example:**
```python
from analysis.shared import create_snowflake_connection

conn = create_snowflake_connection(max_retries=5)
cursor = conn.cursor()
cursor.execute("SELECT * FROM MY_TABLE")
```

### 2. **logging.py** - Standardized Logging
Provides consistent logging setup across all analysis modules.

**Key Functions:**
- `setup_module_logger()` - Create standardized logger
- `log_execution_time()` - Decorator for timing functions
- `log_dataframe_info()` - Log DataFrame statistics
- `log_analysis_start()` / `log_analysis_complete()` - Analysis lifecycle logging

**Example:**
```python
from analysis.shared import setup_module_logger, log_execution_time

logger = setup_module_logger("MyAnalysis")

@log_execution_time(logger)
def process_data():
    # Your code here
    pass
```

### 3. **error_handling.py** - Error Management
Custom exceptions and error handling patterns.

**Custom Exceptions:**
- `AnalysisError` - Base exception
- `DataValidationError` - Data validation failures
- `DataNotFoundError` - Missing data
- `ConfigurationError` - Configuration issues
- `ProcessingError` - Processing failures
- `ReportGenerationError` - Report generation issues

**Key Functions:**
- `retry_on_failure()` - Decorator for automatic retries
- `handle_analysis_error()` - Standardized error handling
- `safe_execute()` - Execute with fallback
- `validate_or_raise()` - Conditional validation

**Example:**
```python
from analysis.shared import retry_on_failure, DataNotFoundError

@retry_on_failure(max_attempts=3, delay=2.0)
def fetch_data():
    # Automatically retries on failure
    return api.get_data()
```

### 4. **data_validation.py** - Data Quality Checks
Validation functions for DataFrames and parameters.

**Key Functions:**
- `validate_dataframe()` - Check DataFrame structure
- `validate_machine_ids()` - Validate equipment IDs
- `validate_date_range()` - Validate date inputs
- `validate_numeric_parameter()` - Validate numeric values
- `check_data_quality()` - Data quality reports
- `validate_schema()` - Schema validation

**Example:**
```python
from analysis.shared import validate_dataframe, validate_machine_ids

# Validate DataFrame
validate_dataframe(df, required_columns=["MACHINE_ID", "DATE"], min_rows=10)

# Validate equipment codes
codes = validate_machine_ids("MX-7110")  # Returns ["MX-7110"]
codes = validate_machine_ids(["MX-7110", "MX-7109"])  # Returns list
```

### 5. **file_operations.py** - File I/O
File handling, path management, and I/O operations.

**Key Functions:**
- `ensure_directory()` - Create directories
- `generate_filename()` / `generate_filepath()` - Standardized file naming
- `safe_write_json()` / `safe_read_json()` - JSON operations
- `temporary_file()` - Context manager for temp files
- `get_file_size_mb()` - Get file size
- `list_files_by_extension()` - Find files

**Example:**
```python
from analysis.shared import generate_filepath, ensure_directory, safe_write_json

# Generate output path
output_path = generate_filepath("output", "report", "xlsx")
# Result: output/report_20241028_160530.xlsx

# Ensure directory exists
ensure_directory("output/reports")

# Write JSON safely
safe_write_json({"status": "success"}, "output/results.json")
```

### 6. **time_utils.py** - Time Formatting
Time formatting, parsing, and calculation utilities.

**Key Functions:**
- `format_time_readable()` - Convert minutes to readable format
- `format_seconds_readable()` - Convert seconds to readable format
- `parse_date_string()` - Parse date with multiple formats
- `parse_date_range()` - Parse and validate date range
- `calculate_business_days()` - Count business days
- `get_timestamp_str()` - Get formatted timestamp

**Example:**
```python
from analysis.shared import format_time_readable, parse_date_range

# Format time
duration = format_time_readable(125.5)  # Returns "2h 5m 30s"

# Parse date range
start, end = parse_date_range("2024-01-01", "2024-12-31")
```

### 7. **constants.py** - Common Constants
Shared constants, thresholds, and configuration values.

**Available Constants:**
- `AnalysisThresholds` - Analysis thresholds (efficiency, duration deviation, etc.)
- `EquipmentStatus` - Equipment status enum
- `AnalysisStatus` - Analysis status enum
- `FilePaths` - Standard file paths
- `DatabaseTables` - Snowflake table names
- `DatabaseSchemas` - Snowflake schema names
- `ColumnNames` - Standard column names
- `TimeConstants` - Time conversion constants
- `AnalysisConfig` - Default configuration
- `ReportConfig` - Report generation config
- `SQLTemplates` - SQL query templates

**Example:**
```python
from analysis.shared import AnalysisThresholds, ColumnNames, DatabaseTables

# Use thresholds
if efficiency > AnalysisThresholds.EFFICIENCY_EXCELLENT:
    print("Excellent performance!")

# Use standard column names
equipment_col = ColumnNames.MACHINE_ID
ct_col = ColumnNames.DURATION

# Use table names
query = f"SELECT * FROM {DatabaseTables.SHOT_DATA}"
```

## 🚀 Quick Start

### Simple Import
```python
from analysis.shared import (
    setup_module_logger,
    create_snowflake_connection,
    validate_machine_ids,
    generate_filepath,
    format_time_readable
)
```

### Complete Example
```python
from analysis.shared import (
    setup_module_logger,
    create_snowflake_connection,
    validate_dataframe,
    validate_machine_ids,
    generate_filepath,
    handle_analysis_error,
    log_execution_time,
    AnalysisThresholds
)

# Setup logging
logger = setup_module_logger("MyAnalysis")

@log_execution_time(logger)
def run_analysis(machine_id: str):
    try:
        # Validate input
        codes = validate_machine_ids(machine_id)
        
        # Connect to database
        conn = create_snowflake_connection()
        cursor = conn.cursor()
        
        # Fetch data
        query = f"SELECT * FROM MY_TABLE WHERE MACHINE_ID = '{codes[0]}'"
        cursor.execute(query)
        df = cursor.fetch_pandas_all()
        
        # Validate data
        validate_dataframe(df, required_columns=["DURATION", "DATE"], min_rows=10)
        
        # Process data
        # ... your analysis logic ...
        
        # Generate output
        output_path = generate_filepath("output", "report", "xlsx")
        # ... save report ...
        
        logger.info(f"✅ Analysis complete: {output_path}")
        return output_path
        
    except Exception as e:
        handle_analysis_error(e, f"analyzing equipment {machine_id}", logger)
```

## 📊 Benefits

### Before Shared Utilities
- ❌ 27+ duplicate logging imports
- ❌ 84+ inconsistent exception handlers
- ❌ Scattered utility functions
- ❌ Inconsistent error messages
- ❌ Duplicate connection logic

### After Shared Utilities
- ✅ Single source of truth
- ✅ Consistent logging and error handling
- ✅ Reduced code duplication
- ✅ Easier maintenance
- ✅ Better testing
- ✅ Improved reliability

## 🔄 Migration Guide

### Step 1: Update Imports
**Before:**
```python
import logging
from shared_utils import create_snowflake_connection
logger = logging.getLogger(__name__)
```

**After:**
```python
from analysis.shared import setup_module_logger, create_snowflake_connection
logger = setup_module_logger("MyModule")
```

### Step 2: Use Standardized Functions
Replace custom implementations with shared utilities:

**Before:**
```python
def validate_equipment(code):
    if not code or not isinstance(code, str):
        raise ValueError("Invalid equipment code")
    return code
```

**After:**
```python
from analysis.shared import validate_machine_ids
codes = validate_machine_ids(code)
```

### Step 3: Use Constants
**Before:**
```python
MAX_DURATION = 999.9
EFFICIENCY_THRESHOLD = 80.0
```

**After:**
```python
from analysis.shared import AnalysisThresholds
max_duration = AnalysisThresholds.MAX_ACCEPTABLE_CT
threshold = AnalysisThresholds.EFFICIENCY_GOOD
```

## 📚 Full API Reference

See individual module docstrings for complete API documentation:
- `help(analysis.shared.connections)`
- `help(analysis.shared.logging)`
- `help(analysis.shared.error_handling)`
- `help(analysis.shared.data_validation)`
- `help(analysis.shared.file_operations)`
- `help(analysis.shared.time_utils)`
- `help(analysis.shared.constants)`

## 🧪 Testing

All shared utilities include comprehensive docstrings and examples.
To test imports:

```bash
python -c "from analysis.shared import *; print('✅ All utilities loaded')"
```

## 📝 Notes

- **Backward Compatibility**: The old `shared_utils.py` is kept for backward compatibility
- **Migration**: Gradually migrate existing modules to use the new shared utilities
- **Documentation**: All functions include docstrings with examples
- **Type Hints**: All functions use proper type hints for better IDE support

## 🔗 Related Documentation

- See `analysis/shared_utils.py` for legacy utilities (kept for backward compatibility)
- See individual analysis module documentation for usage examples
- See `.env.template` for required environment variables

---

**Questions or Issues?** Contact the maintainer or check individual module docstrings.



