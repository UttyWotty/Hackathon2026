Technical Debt Report - Manufacturing API
Here's the comprehensive analysis of technical debt in your repository:

CRITICAL ISSUES (3 items)
Issue	File	Description
Hardcoded Credentials	.env	Snowflake password and SMTP credentials exposed
<!-- Duplicate execute_tool	core/tools_config.py + tool_dispatcher.py	Two implementations with potentially different logic (RESOLVED: consolidated to core/tools/executor.py, tools_config.py re-exports) -->
<!-- Misplaced Docstring	analysis/rca/core_analysis/industry_standards.py	Docstring after imports (RESOLVED: fixed to 3-sentence summary format per CLAUDE.md Rule 2) -->
<!-- HIGH SEVERITY - Files Exceeding 500 Lines (CLAUDE.md Violation) - ALL RESOLVED
All 20 files that exceeded 500 lines have been split into smaller modules. Each is now under 500 lines.
Extracted modules: risk_classifier, rca_visualizations, rca_report_formatter, pareto_scrap_detector, pareto_ct_deviations, pareto_downtime, pareto_issue_analyzer, pareto_recommendations, five_whys_metrics, five_whys_time_analysis, five_whys_data_driven, five_whys_equipment, five_whys_comprehensive_metrics, roi_summary, ppt_slide_builders, ppt_insight_generators, audit_compliance_router, mcp_tool_utils, mcp_jobs_router, email_helpers, token_roles, job_result_handler, analytics_tool_defs.
analysis/rca/core_analysis/pareto_analysis_per_tool.py	1866->375	RESOLVED: split into pareto_scrap_detector, pareto_ct_deviations, pareto_downtime, pareto_issue_analyzer, pareto_recommendations
analysis/rca/core_analysis/five_whys_analysis.py	1837->448	RESOLVED: split into five_whys_metrics, five_whys_time_analysis, five_whys_data_driven, five_whys_equipment, five_whys_comprehensive_metrics
core/tools_config.py	1248->25	RESOLVED: split into core/tools/definitions.py + core/tools/analytics_tool_defs.py
routers/visualization_router.py	1017->498	RESOLVED: natural reduction during refactoring
analysis/runrate/core/session_analyzer.py	891->394	RESOLVED: constants extracted to shared, methods simplified
analysis/shared/weekly_comparison_ppt.py	880->421	RESOLVED: split into ppt_slide_builders, ppt_insight_generators
routers/mcp_router.py	840->489	RESOLVED: split into mcp_tool_utils, mcp_jobs_router
routers/analytics_router.py	840->481	RESOLVED: natural reduction during refactoring
routers/audit_router.py	818->456	RESOLVED: split into audit_compliance_router
analysis/shared/summary_generator.py	802->462	RESOLVED: split into roi_summary
analysis/capacity/core/metrics.py	665->457	RESOLVED: constants extracted to shared
services/config/features/analytics/tools/master_table_tools.py	646->428	RESOLVED: natural reduction
analysis/tooling_eol/core/eol_predictor.py	624->429	RESOLVED: natural reduction
services/infrastructure/auth/token_manager.py	596->458	RESOLVED: split into token_roles
analysis/rca/core_analysis/advanced_analysis.py	589->405	RESOLVED: split into risk_classifier, rca_visualizations
analysis/rca/core_analysis/industry_standards.py	585->497	RESOLVED: natural reduction
analysis/rca/core_analysis/root_cause_analysis_pipeline.py	582->407	RESOLVED: split into rca_report_formatter
services/infrastructure/scheduler/background_scheduler.py	577->370	RESOLVED: split into job_result_handler
services/infrastructure/audit/audit_logger.py	543->478	RESOLVED: natural reduction
routers/email_router.py	542->366	RESOLVED: split into email_helpers
-->
MEDIUM SEVERITY ISSUES
Category	Count	Examples
/////Broad Exception Handling	~115	except Exception: masks specific errors/////
Missing Return Type Hints	~353	Functions without -> Type annotations
////TODO/FIXME Comments	4+	Incomplete implementations in session_analyzer.py/////
Hardcoded Config Values	Multiple	Equipment cavity mappings in config.py
Configuration Scattered	4+ locations	.env, config.py, industry_standards.py, routers
LOW SEVERITY ISSUES
Category	Issue
Naming Inconsistencies	Mix of ct vs cycle_time, inconsistent CONSTANT_CASE
Test Coverage	Only 11 test files for 258 Python files (<5% coverage)
////Import Organization	Not following isort conventions////
////Logging Patterns	Mixed approaches (standard vs custom, with/without emoji)////
Missing mypy.ini	No strict type checking configuration
TEST COVERAGE GAP

Total Python files:     258
Total test files:        11
Estimated coverage:     <5%

Untested modules:
- analysis/capacity/     (14 files)
- analysis/rca/          (12 files)
- analysis/runrate/      (18 files)
- analysis/ct_*/         (24 files)
- analysis/tooling_eol/  (12 files)
- analysis/roi/          (8 files)
- services/              (30+ files)
SUMMARY BY SEVERITY
Severity	Count
CRITICAL	3
HIGH	20+ (files over 500 lines)
MEDIUM	500+ (type hints, exceptions, TODOs)
LOW	Various
RECOMMENDED PRIORITY
Phase 1 (Immediate)

Secure credentials - remove from .env, use secrets manager
<!-- Consolidate duplicate execute_tool implementations (RESOLVED) -->
<!-- Fix industry_standards.py docstring placement (RESOLVED) -->
Phase 2 (Near-term)

<!-- Break down the 20 files exceeding 500 lines (RESOLVED: all 20 files now under 500 lines) -->
Add tests for critical analysis modules
Replace broad exception catches
Phase 3 (Ongoing)

Add missing type hints
Centralize configuration
Standardize logging patterns