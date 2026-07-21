# Manufacturing Analysis Modules

Comprehensive analysis modules for manufacturing operations, focused on injection molding processes.

## Architecture

The analysis modules follow a modular architecture with well-defined responsibilities:

```
analysis/
├── capacity/           # Multi-OEE capacity and performance analysis
├── ct_deviation/       # Cycle time deviation metrics
├── ct_efficiency/      # Enhanced efficiency analysis with benchmarking
├── rca/                # Root cause analysis pipeline
├── roi/                # Return on investment analysis
├── runrate/            # RunRate analysis with Excel generation
├── shared/             # Shared utilities (connections, logging, error handling, etc.)
└── tooling_eol/        # End-of-life prediction
```

## Module Overview

### 1. Capacity Analysis (`capacity/`)
Multi-OEE capacity and performance analysis with session-based metrics.

**Key Features:**
- Session-based analysis (midnight OR 8-hour break splits)
- Multi-cavity mold support (1 shot = N parts)
- OEE breakdown: Availability × Performance × Quality
- 6 OEE targets (50%-100%) for scenario planning
- Excel reports with formatted sheets per OEE target
- Interactive HTML dashboards with Plotly charts

**Usage:**
```python
from capacity import main

# Interactive mode
main(interactive=True)

# Direct parameters
main(
    equipment_code="EMA-4104",
    supplier_name="Vantis industries",
    start="2025-01-01",
    end="2025-12-31"
)
```

### 2. Cycle Time Deviation (`ct_deviation/`)
Comprehensive CT deviation analysis with categorization and scoring.

**Key Features:**
- 5-tier deviation categorization (Excellent to Critical)
- Efficiency and stability scoring
- Shot-level analysis (above/below/on target)
- Statistical confidence intervals
- AI-powered recommendations
- Excel and PDF reporting

**Usage:**
```python
from ct_deviation import CTDeviationAnalyzer

analyzer = CTDeviationAnalyzer()
analyzer.fetch_data(equipment_code="EMA-4104")
analyzer.generate_report()
```

### 3. Cycle Time Efficiency (`ct_efficiency/`)
Enhanced efficiency analysis with supplier benchmarking and anomaly detection.

**Key Features:**
- Supplier benchmarking with tier classification
- Tool consistency scoring
- Anomaly detection (Z-score, IQR, Isolation Forest)
- Data quality assessment
- Predictive modeling
- Interactive Plotly visualizations

**Usage:**
```python
from ct_efficiency import EnhancedCTEfficiencyAnalyzer

analyzer = EnhancedCTEfficiencyAnalyzer(config={...})
analyzer.connect_snowflake()
analyzer.fetch_data(equipment_code="EMA-4104")
analyzer.run_comprehensive_analysis()
```

### 4. ROI Analysis (`roi/`)
Return on Investment analysis for cycle time efficiency.

**Key Features:**
- Cycle time classification (WITHIN/FASTER/SLOWER)
- Time metrics (hours gained/lost)
- Efficiency calculations
- Process stability metrics
- Multi-sheet Excel reports with formulas
- Supplier-year grouping

**Usage:**
```python
from roi import ROIAnalyzer

analyzer = ROIAnalyzer()
valid_df, suspicious_df = analyzer.analyze(
    supplier_names=["Vantis industries"],
    start_date="2025-01-01",
    end_date="2025-12-31"
)
report_path = analyzer.generate_excel_report(valid_df, suspicious_df)
```

### 5. RunRate Analysis (`runrate/`)
Session-based production rate analysis with Excel formula generation.

**Key Features:**
- 8-hour threshold stop detection
- Per-session mode CT calculation
- MTTR/MTBF reliability metrics
- Excel reports with live formulas
- Daily trends with charts
- Session aggregation logic

**Usage:**
```python
from runrate.analyzer import RunRateAnalyzer

analyzer = RunRateAnalyzer()
results = analyzer.analyze(
    equipment_code="EMA-4104",
    start_date="2025-01-01",
    end_date="2025-12-31"
)
analyzer.generate_excel_report(results)
```

### 6. Root Cause Analysis (`rca/`)
Comprehensive RCA pipeline with Pareto analysis and Five Whys.

**Key Features:**
- Pareto analysis per tool and supplier
- Advanced statistical analysis
- Five Whys methodology
- Industry standards comparison
- Interactive Streamlit dashboards
- Supplier-specific analysis

**Modules:**
- `pareto_analysis_per_tool.py`: Tool-level Pareto analysis
- `pareto_analysis_supplier.py`: Supplier-level Pareto  
- `advanced_analysis.py`: Statistical deep dive
- `five_whys_analysis.py`: Root cause investigation
- `streamlit_dashboard.py`: Interactive visualization

### 7. LLM Integration (`llm/`)
AI-powered recommendations using AWS Bedrock.

**Features:**
- AWS Bedrock Claude integration
- Contextual analysis recommendations
- Message chain management
- Credential helper utilities

### 8. Tooling EOL (`tooling_eol/`)
End-of-life prediction for manufacturing tools.

**Features:**
- Shot count tracking
- Wear estimation
- Maintenance event prediction
- Remaining life calculations

## Design Patterns

### 1. Modular Architecture
Each analysis module is self-contained with clear interfaces:
- `__init__.py`: Module documentation and exports
- `analyzer.py` / `core/`: Main analysis logic
- `models/`: Data models and configurations
- `reporting/`: Report generation utilities

### 2. Delegation Pattern
Complex functions (like Excel generation) use delegation:
- Clean public API in modular files
- Delegation to proven implementation
- Extensive documentation of behavior
- Clear design decisions documented

### 3. Configuration Management
Modules use configuration objects for flexibility:
- Dataclass-based configurations
- Default values provided
- Easy customization per use case

### 4. Database Abstraction
Clean database layer separation:
- Connection management in dedicated classes
- SQL query building with parameterization
- Snowflake Snowpark and connector support
- Shared utility functions

## Common Patterns

### Error Handling
```python
try:
    result = analyzer.analyze(...)
except Exception as e:
    logging.error(f"Analysis failed: {e}")
    # Graceful degradation or user notification
```

### Logging
All modules use Python's `logging` module:
```python
import logging

logging.info("✅ Analysis completed")
logging.warning("⚠️ Data quality issue detected")
logging.error("❌ Critical failure")
```

### Data Validation
```python
if df.empty:
    logging.warning("No data found")
    return pd.DataFrame()

# Validate required columns
required_cols = ["EQUIPMENT_CODE", "CT", "APPROVED_CT"]
missing = set(required_cols) - set(df.columns)
if missing:
    raise ValueError(f"Missing columns: {missing}")
```

## Dependencies

### Core Dependencies
- `pandas`: Data manipulation
- `numpy`: Numerical operations
- `snowflake-connector-python`: Database connectivity
- `snowflake-snowpark-python`: Advanced Snowflake operations

### Visualization
- `plotly`: Interactive charts
- `matplotlib`: Static plots
- `seaborn`: Statistical visualizations

### Reporting
- `openpyxl`: Excel generation
- `xlsxwriter`: Advanced Excel formatting
- `reportlab`: PDF generation

### Analysis
- `scipy`: Statistical functions
- `scikit-learn`: Machine learning
- `statsmodels`: Time series analysis

### AI Integration
- `boto3`: AWS SDK
- `langchain`: LLM orchestration

## Testing Strategy

### Unit Tests
Each module should have unit tests for:
- Core calculation functions
- Data validation
- Configuration handling

### Integration Tests
Test database connections and data flow:
- Snowflake connection
- Query execution
- Data transformation pipeline

### End-to-End Tests
Full workflow validation:
- Data fetch → Analysis → Report generation
- Check output file creation
- Validate report contents

## Best Practices

### 1. Always Use Type Hints
```python
def analyze(self, df: pd.DataFrame, config: Config) -> Results:
    """Analyze data with type safety."""
    pass
```

### 2. Document Functions Thoroughly
```python
def calculate_efficiency(shots: int, time_sec: float) -> float:
    """
    Calculate production efficiency.
    
    Args:
        shots: Number of valid shots produced
        time_sec: Total production time in seconds
        
    Returns:
        Efficiency percentage (0-100)
        
    Raises:
        ValueError: If time_sec is zero or negative
    """
    if time_sec <= 0:
        raise ValueError("Time must be positive")
    return (shots / time_sec) * 100
```

### 3. Use Dataclasses for Configuration
```python
from dataclasses import dataclass

@dataclass
class AnalysisConfig:
    """Configuration for analysis parameters."""
    min_shots: int = 100
    max_ct: float = 999.9
    delta_tolerance: float = 0.05
```

### 4. Centralize Database Connections
```python
from shared_utils import get_snowflake_connection_params

def connect():
    """Get standardized Snowflake connection."""
    params = get_snowflake_connection_params()
    return snowflake.connector.connect(**params)
```

### 5. Validate Data Early
```python
def validate_data(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and clean input data."""
    # Remove invalid CT values
    df = df[df["CT"] < 999.9]
    
    # Ensure positive values
    df = df[df["CT"] > 0]
    
    # Drop nulls
    df = df.dropna(subset=["EQUIPMENT_CODE", "CT"])
    
    return df
```

## Refactoring History

### 2025-10-26: Major Refactoring
1. **RunRate Module**
   - Completed TODO placeholders
   - Documented delegation pattern
   - Clarified design decisions

2. **ROI Module**
   - Already well-structured
   - Added comprehensive module documentation
   - Verified all docstrings present

3. **Capacity, CT Deviation, CT Efficiency**
   - Created comprehensive __init__ files
   - Documented features and usage
   - Added module-level documentation

4. **Architecture Documentation**
   - Created this README
   - Documented patterns and best practices
   - Provided usage examples

### Design Decision: Monolithic vs. Modular
For modules with complex, tightly-coupled logic (like Excel generation):
- **Chose**: Delegation pattern with wrapper functions
- **Rationale**: 
  - Maintains working, tested implementation
  - Provides clean API
  - Avoids high-risk refactoring
  - Documents design clearly

## Future Enhancements

### Short Term
- [ ] Add unit tests for all core functions
- [ ] Standardize error handling across modules
- [ ] Create shared base classes for analyzers
- [ ] Unified configuration management

### Medium Term
- [ ] REST API endpoints for each module
- [ ] Async processing for large datasets
- [ ] Caching layer for repeated queries
- [ ] Monitoring and alerting

### Long Term
- [ ] Real-time streaming analysis
- [ ] Advanced ML models for predictions
- [ ] Multi-tenant support
- [ ] Cloud-native deployment

## Contributing

When adding or modifying modules:

1. **Follow existing patterns**
   - Use dataclasses for configs
   - Implement proper logging
   - Add comprehensive docstrings

2. **Document design decisions**
   - Why this approach?
   - What alternatives were considered?
   - Trade-offs made

3. **Write tests**
   - Unit tests for functions
   - Integration tests for workflows
   - Document test coverage

4. **Update this README**
   - Add new module documentation
   - Update architecture diagrams
   - Note breaking changes

## Support

For questions or issues:
- Check module-specific `__init__.py` documentation
- Review code examples in this README
- Check inline comments in source files
- Review git history for context

## License

Internal use only - Proprietary

---

**Last Updated**: 2025-10-26  
**Maintainer**: Utku Gulbardak

