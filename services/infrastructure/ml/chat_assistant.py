"""
Manufacturing Chat Assistant - Unified AI interface for production analytics.

Combines LLM capabilities with data access to provide intelligent manufacturing insights,
SQL generation, report summarization, and conversational analytics.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .mlx_llm import MlxLLMService, mlx_llm

logger = logging.getLogger(__name__)


class ChatIntent(str, Enum):
    """Detected intent from user message."""

    RUN_ANALYSIS = "run_analysis"  # User wants to run a real analysis tool
    QUERY_DATA = "query_data"  # User wants to query production data
    ANALYZE_METRICS = "analyze_metrics"  # User wants analysis of metrics
    EXPLAIN_REPORT = "explain_report"  # User wants report explanation
    GENERATE_SQL = "generate_sql"  # User wants SQL query
    GENERAL_CHAT = "general_chat"  # General conversation
    TROUBLESHOOT = "troubleshoot"  # User has a problem to solve
    COMPARE = "compare"  # User wants to compare data
    FORECAST = "forecast"  # User wants predictions


@dataclass
class ConversationContext:
    """Maintains conversation state and history."""

    session_id: str
    messages: List[Dict[str, str]] = field(default_factory=list)
    current_data: Optional[Dict[str, Any]] = None
    current_equipment: Optional[str] = None
    current_date_range: Optional[Tuple[str, str]] = None
    last_sql: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str) -> None:
        """Add message to conversation history."""
        self.messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(),
            }
        )
        # Keep last 20 messages for context
        if len(self.messages) > 20:
            self.messages = self.messages[-20:]

    def get_chat_messages(self) -> List[Dict[str, str]]:
        """Get messages in LLM chat format."""
        return [{"role": m["role"], "content": m["content"]} for m in self.messages]


# Snowflake schema context for SQL generation
SNOWFLAKE_SCHEMA = """
## Available Tables

### MFG_ANALYTICS.SHOT_DATA
Production shot data from injection molding machines.
Columns:
- EQUIPMENT_CODE (VARCHAR): Machine identifier (e.g., 'EMA-4104')
- LOCAL_SHOT_TIME (TIMESTAMP): When shot occurred
- ACTUAL_CT (FLOAT): Actual cycle time in seconds
- TARGET_CT (FLOAT): Target cycle time
- SHOT_DIFF_SEC (FLOAT): Time since previous shot
- SESSION_ID (VARCHAR): Production session identifier
- PART_NUMBER (VARCHAR): Part being produced

### MFG_ANALYTICS.EQUIPMENT_MASTER
Equipment reference data.
Columns:
- EQUIPMENT_CODE (VARCHAR): Machine identifier
- PLANT_CODE (VARCHAR): Plant location
- EQUIPMENT_TYPE (VARCHAR): Type of machine
- STATUS (VARCHAR): Current status

### MFG_ANALYTICS.PRODUCTION_SUMMARY
Daily production summaries.
Columns:
- EQUIPMENT_CODE (VARCHAR): Machine identifier
- PRODUCTION_DATE (DATE): Date
- TOTAL_SHOTS (INT): Total shots produced
- EFFICIENCY_PCT (FLOAT): Efficiency percentage
- DOWNTIME_MIN (FLOAT): Total downtime in minutes
- MTTR_MIN (FLOAT): Mean Time To Repair
- MTBF_MIN (FLOAT): Mean Time Between Failures

## Key Metrics
- Efficiency = Normal Shots / Total Shots × 100
- Stability Index = Production Time / Total Run Time × 100
- MTTR = Total Downtime / Stop Events
- MTBF = Production Time / Stop Events
"""


SYSTEM_PROMPT = """You are an expert Manufacturing Analytics Assistant for injection molding operations.

## Your Capabilities

### 1. Analysis Types You Can Help With:

**ROI Analysis** - Return on Investment
- Cost savings, production efficiency, uptime, financial returns
- Daily/weekly/monthly aggregation
- Valid vs suspicious record filtering

**RunRate Analysis** - Production Run Rate
- MTTR (Mean Time To Repair) - lower is better
- MTBF (Mean Time Between Failures) - higher is better
- Stop detection, efficiency tracking, session analysis
- Risk Tower: 4-week rolling RAG status (Red <50%, Amber 50-70%, Green ≥70%)

**RCA Analysis** - Root Cause Analysis
- Pareto analysis (80/20 rule) for top issues
- 5 Whys methodology for root cause identification
- Downtime, scrap rate, equipment & supplier analysis
- Actionable recommendations with priorities

**CT Efficiency Analysis** - Cycle Time Efficiency
- Efficiency calculation and scoring
- Supplier benchmarking and ranking
- Tier classification (Top/High/Medium/Low/Poor)
- Tool consistency scoring

**CT Deviation Analysis** - Cycle Time Deviation
- Deviation from approved specifications
- Performance categorization (Excellent to Critical)
- Above/below/on-target shot analysis
- Equipment and supplier comparison

**Tooling EOL Analysis** - End-of-Life Prediction
- Remaining shots/days estimation
- Utilization pattern tracking
- Degradation prediction with confidence scores
- Early warning flags for overutilization

**Capacity Analysis** - OEE (Overall Equipment Effectiveness)
- Availability, Performance, Quality metrics
- Multi-target OEE scenarios (50%-100%)
- Bottleneck identification
- Production output vs optimal output

### 2. Other Capabilities:
- **SQL Generation**: Snowflake SQL queries for data retrieval
- **Report Interpretation**: Explain any analysis report
- **Troubleshooting**: Diagnose production issues
- **Recommendations**: Actionable improvement suggestions

## Key Domain Knowledge

**Stop Detection (RunRate)**:
- Hard Stop: CT ≥ 999.9
- Abnormal Cycle: CT outside ±5% of mode
- Time Gap: gap > prev_CT + 2.0 seconds
- Run Interval: 8-hour gap creates new production run

**OEE Formula**:
OEE = Availability × Performance × Quality
- Availability = Run Time / Planned Production Time
- Performance = (Ideal Cycle Time × Total Count) / Run Time
- Quality = Good Count / Total Count

**Efficiency Tiers**:
- Top Performer: ≥95%
- High Performer: 85-94%
- Medium Performer: 70-84%
- Low Performer: 50-69%
- Poor Performer: <50%

## Response Guidelines
- Explain metrics in practical business terms
- Highlight concerning trends or anomalies
- Provide specific, actionable recommendations
- Use manufacturing terminology appropriately
- When generating SQL, use Snowflake syntax with proper date filters
"""


class ManufacturingChatAssistant:
    """
    Unified AI assistant for manufacturing analytics.

    Provides conversational interface for data queries, analysis,
    report summarization, and SQL generation.
    """

    def __init__(self, llm_service: Optional[MlxLLMService] = None):
        """Initialize chat assistant."""
        self.llm = llm_service or mlx_llm
        self.conversations: Dict[str, ConversationContext] = {}
        logger.info("Manufacturing Chat Assistant initialized")

    def get_or_create_conversation(self, session_id: str) -> ConversationContext:
        """Get existing conversation or create new one."""
        if session_id not in self.conversations:
            self.conversations[session_id] = ConversationContext(session_id=session_id)
            logger.info(f"Created new conversation: {session_id}")
        return self.conversations[session_id]

    def detect_intent(self, message: str) -> ChatIntent:
        """Detect user intent from message."""
        from .tool_executor import is_analysis_request

        message_lower = message.lower()

        # Check for real analysis request FIRST (highest priority)
        if is_analysis_request(message):
            return ChatIntent.RUN_ANALYSIS

        # SQL generation keywords
        if any(kw in message_lower for kw in ["sql", "query", "select", "from table"]):
            return ChatIntent.GENERATE_SQL

        # Data query keywords
        if any(
            kw in message_lower
            for kw in ["show me", "get", "retrieve", "what is the", "how many"]
        ):
            return ChatIntent.QUERY_DATA

        # Analysis keywords
        if any(
            kw in message_lower
            for kw in ["analyze", "analysis", "why", "explain", "what does"]
        ):
            return ChatIntent.ANALYZE_METRICS

        # Report keywords
        if any(
            kw in message_lower
            for kw in ["report", "runrate", "risk tower", "summary", "summarize"]
        ):
            return ChatIntent.EXPLAIN_REPORT

        # Troubleshooting keywords
        if any(
            kw in message_lower
            for kw in ["problem", "issue", "fix", "troubleshoot", "wrong", "error"]
        ):
            return ChatIntent.TROUBLESHOOT

        # Comparison keywords
        if any(
            kw in message_lower
            for kw in ["compare", "versus", "vs", "difference between"]
        ):
            return ChatIntent.COMPARE

        # Forecast keywords
        if any(
            kw in message_lower
            for kw in ["predict", "forecast", "will", "future", "trend"]
        ):
            return ChatIntent.FORECAST

        return ChatIntent.GENERAL_CHAT

    async def chat(
        self,
        message: str,
        session_id: str = "default",
        data_context: Optional[Dict[str, Any]] = None,
        equipment_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process chat message and generate response.

        Args:
            message: User message
            session_id: Conversation session ID
            data_context: Optional data context for analysis
            equipment_code: Optional equipment filter

        Returns:
            Response with content, intent, and any generated artifacts
        """
        context = self.get_or_create_conversation(session_id)
        context.add_message("user", message)

        # Update context
        if data_context:
            context.current_data = data_context
        if equipment_code:
            context.current_equipment = equipment_code

        # Detect intent
        intent = self.detect_intent(message)

        # Build response based on intent
        try:
            if intent == ChatIntent.RUN_ANALYSIS:
                response = await self._handle_run_analysis(message, context)
            elif intent == ChatIntent.GENERATE_SQL:
                response = self._handle_sql_generation(message, context)
            elif intent == ChatIntent.ANALYZE_METRICS:
                response = self._handle_analysis(message, context)
            elif intent == ChatIntent.EXPLAIN_REPORT:
                response = self._handle_report_explanation(message, context)
            elif intent == ChatIntent.TROUBLESHOOT:
                response = self._handle_troubleshooting(message, context)
            else:
                response = self._handle_general_chat(message, context)

            context.add_message("assistant", response["content"])
            response["intent"] = intent.value
            response["session_id"] = session_id

            return response

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            error_response = {
                "content": f"I encountered an error processing your request: {str(e)}",
                "intent": intent.value,
                "session_id": session_id,
                "error": str(e),
            }
            context.add_message("assistant", error_response["content"])
            return error_response

    async def _handle_run_analysis(
        self,
        message: str,
        context: ConversationContext,
    ) -> Dict[str, Any]:
        """Run a real analysis tool and summarize the results."""
        from .tool_executor import (
            detect_analysis_type,
            execute_analysis,
            extract_parameters,
            format_result_for_llm,
            get_missing_params_message,
        )

        tool_name = detect_analysis_type(message)
        if not tool_name:
            return {
                "content": "I couldn't determine which analysis to run. "
                "Available: RunRate, ROI, RCA, CT Efficiency, CT Deviation, "
                "Tooling EOL, Capacity/OEE.",
                "type": "error",
            }

        params = extract_parameters(message, tool_name)

        # Check for missing required parameters
        missing_msg = get_missing_params_message(tool_name, params)
        if missing_msg:
            return {"content": missing_msg, "type": "missing_params"}

        # Execute the real analysis
        tool_display = tool_name.replace("run_", "").replace("_", " ").title()
        logger.info("Running real analysis: %s with params %s", tool_name, params)

        try:
            result = await execute_analysis(tool_name, params)
        except Exception as e:
            logger.error("Analysis execution failed: %s", e, exc_info=True)
            return {
                "content": f"Failed to run {tool_display}: {str(e)}",
                "type": "error",
            }

        if result.get("status") == "error":
            return {
                "content": f"**{tool_display}** encountered an error:\n\n"
                f"{result.get('error', 'Unknown error')}",
                "type": "error",
            }

        # Store results in context for follow-up questions
        context.current_data = result

        # Format results and have LLM summarize
        result_str = format_result_for_llm(result, tool_name)

        prompt = (
            f"I just ran a **{tool_display}** with these parameters:\n"
            f"{json.dumps(params, default=str)}\n\n"
            f"Here are the REAL results from our production database:\n\n"
            f"{result_str}\n\n"
            f"Please provide a clear summary of these results. "
            f"Highlight key metrics, any concerns, and recommendations."
        )

        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="fast",
            max_tokens=2048,
        )

        # Build response with output files if available
        output_files = result.get("output_files", {})
        file_info = ""
        if output_files:
            file_info = "\n\n**Generated Files:**\n"
            for ftype, fpath in output_files.items():
                file_info += f"- {ftype}: `{fpath}`\n"

        return {
            "content": response.content + file_info,
            "type": "analysis_result",
            "model": response.model,
            "output_files": output_files,
            "analysis_tool": tool_name,
            "parameters": params,
        }

    def _handle_sql_generation(
        self,
        message: str,
        context: ConversationContext,
    ) -> Dict[str, Any]:
        """Generate SQL query from natural language."""
        # Build prompt with schema context
        prompt = f"""Generate a Snowflake SQL query for the following request:

{message}

{f"Equipment filter: {context.current_equipment}" if context.current_equipment else ""}

Requirements:
- Use proper Snowflake SQL syntax
- Include appropriate WHERE clauses for date/equipment filters
- Format the query for readability
- Only output the SQL query, no explanations
"""

        sql = self.llm.generate_sql(prompt, schema_context=SNOWFLAKE_SCHEMA)
        context.last_sql = sql

        # Generate explanation
        explanation = self.llm.quick_response(
            f"Briefly explain what this SQL query does (1-2 sentences): {sql}"
        )

        return {
            "content": f"Here's the SQL query:\n\n```sql\n{sql}\n```\n\n{explanation}",
            "sql": sql,
            "type": "sql_generation",
        }

    def _handle_analysis(
        self,
        message: str,
        context: ConversationContext,
    ) -> Dict[str, Any]:
        """Handle metrics analysis request."""
        data_str = ""
        if context.current_data:
            data_str = f"\n\nCurrent data context:\n{json.dumps(context.current_data, indent=2, default=str)}"

        prompt = f"{message}{data_str}"

        # Use reasoning model only when actual data is provided, otherwise fast
        use_case = "reasoning" if context.current_data else "fast"
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case=use_case,
            max_tokens=2048,
        )

        return {
            "content": response.content,
            "type": "analysis",
            "model": response.model,
        }

    def _handle_report_explanation(
        self,
        message: str,
        context: ConversationContext,
    ) -> Dict[str, Any]:
        """Explain report or summarize findings."""
        data_str = ""
        if context.current_data:
            data_str = f"\n\nReport data:\n{json.dumps(context.current_data, indent=2, default=str)}"

        prompt = f"""As a manufacturing analytics expert, explain the following report or finding:

{message}{data_str}

Provide:
1. Key findings in plain language
2. What these metrics mean for production
3. Any concerns or areas needing attention
4. Actionable recommendations
"""

        # Use reasoning model only when actual report data is provided
        use_case = "reasoning" if context.current_data else "fast"
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case=use_case,
            max_tokens=2048,
        )

        return {
            "content": response.content,
            "type": "report_explanation",
            "model": response.model,
        }

    def _handle_troubleshooting(
        self,
        message: str,
        context: ConversationContext,
    ) -> Dict[str, Any]:
        """Handle troubleshooting requests."""
        data_str = ""
        if context.current_data:
            data_str = f"\n\nRelevant data:\n{json.dumps(context.current_data, indent=2, default=str)}"

        prompt = f"""As a manufacturing troubleshooting expert, help with this issue:

{message}{data_str}

Provide:
1. Potential root causes (most likely first)
2. Diagnostic steps to confirm the cause
3. Recommended solutions
4. Preventive measures for the future
"""

        # Use reasoning only when data context is available
        use_case = "reasoning" if context.current_data else "fast"
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case=use_case,
            max_tokens=2048,
        )

        return {
            "content": response.content,
            "type": "troubleshooting",
            "model": response.model,
        }

    def _handle_general_chat(
        self,
        message: str,
        context: ConversationContext,
    ) -> Dict[str, Any]:
        """Handle general conversation."""
        messages = context.get_chat_messages()

        response = self.llm.chat(
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
            use_case="fast",
            max_tokens=1024,
        )

        return {
            "content": response.content,
            "type": "general",
            "model": response.model,
        }

    def summarize_runrate_report(
        self,
        report_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate executive summary of RunRate report.

        Args:
            report_data: RunRate analysis results

        Returns:
            Summary with key findings and recommendations
        """
        prompt = f"""Analyze this RunRate production report and provide an executive summary:

{json.dumps(report_data, indent=2, default=str)}

Structure your response as:

## Executive Summary
(2-3 sentence overview)

## Key Metrics
- Efficiency: [value and interpretation]
- Stability Index: [value and interpretation]
- MTTR/MTBF: [values and what they indicate]

## Concerns
(List any metrics outside acceptable ranges)

## Recommendations
(Specific actions to improve performance)
"""

        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=2048,
        )

        return {
            "summary": response.content,
            "model": response.model,
            "report_type": "runrate",
        }

    def summarize_risk_tower(
        self,
        risk_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Generate executive summary of Risk Tower analysis.

        Args:
            risk_data: Risk Tower results per equipment

        Returns:
            Summary with risk rankings and action items
        """
        # Count by RAG status
        red_count = sum(1 for r in risk_data if r.get("RAG_STATUS") == "Red")
        amber_count = sum(1 for r in risk_data if r.get("RAG_STATUS") == "Amber")
        green_count = sum(1 for r in risk_data if r.get("RAG_STATUS") == "Green")

        prompt = f"""Analyze this Risk Tower report and provide an executive summary:

Equipment Count: {len(risk_data)}
- Red (Critical): {red_count}
- Amber (Moderate): {amber_count}
- Green (Stable): {green_count}

Detailed Data:
{json.dumps(risk_data[:10], indent=2, default=str)}
{"(showing top 10 highest risk)" if len(risk_data) > 10 else ""}

Structure your response as:

## Risk Overview
(Overall health assessment)

## Critical Equipment (Red Status)
(List equipment needing immediate attention with primary risk factors)

## Watch List (Amber Status)
(Equipment trending toward problems)

## Declining Trends
(Equipment with stability declining week-over-week)

## Priority Actions
(Top 3-5 immediate actions ranked by impact)
"""

        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=2048,
        )

        return {
            "summary": response.content,
            "model": response.model,
            "report_type": "risk_tower",
            "stats": {
                "total": len(risk_data),
                "red": red_count,
                "amber": amber_count,
                "green": green_count,
            },
        }

    def explain_anomaly(
        self,
        anomaly_data: Dict[str, Any],
        historical_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Explain a detected anomaly.

        Args:
            anomaly_data: Anomaly detection results
            historical_context: Optional historical patterns

        Returns:
            Explanation with probable causes
        """
        prompt = f"""An anomaly was detected in manufacturing data. Analyze and explain:

Anomaly Details:
{json.dumps(anomaly_data, indent=2, default=str)}

{f"Historical Context: {historical_context}" if historical_context else ""}

Provide:
1. What the anomaly indicates
2. Most likely causes (ranked by probability)
3. Potential impact on production
4. Recommended immediate actions
5. Long-term preventive measures
"""

        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=1536,
        )

        return {
            "explanation": response.content,
            "model": response.model,
            "anomaly_type": anomaly_data.get("type", "unknown"),
        }

    def summarize_roi_report(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary of ROI analysis report."""
        prompt = f"""Analyze this ROI (Return on Investment) analysis report and provide an executive summary:

{json.dumps(report_data, indent=2, default=str)}

Structure your response as:

## Executive Summary
(2-3 sentence overview of ROI findings)

## Financial Impact
- Cost Savings: [value and context]
- ROI Percentage: [value and interpretation]
- Payback Period: [if available]

## Production Metrics
- Uptime Improvement: [value]
- Efficiency Gains: [value]

## Key Insights
(Top 3 findings that drive the ROI)

## Recommendations
(Actions to maximize ROI)
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=2048,
        )
        return {
            "summary": response.content,
            "model": response.model,
            "report_type": "roi",
        }

    def summarize_rca_report(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary of RCA (Root Cause Analysis) report."""
        prompt = f"""Analyze this Root Cause Analysis (RCA) report and provide an executive summary:

{json.dumps(report_data, indent=2, default=str)}

Structure your response as:

## Executive Summary
(2-3 sentence overview of root cause findings)

## Top Issues (Pareto Analysis)
(List the top 3-5 issues causing 80% of problems)

## Root Causes Identified
(Main root causes from 5 Whys analysis)

## Impact Assessment
- Downtime Impact: [hours/cost]
- Quality Impact: [scrap rate, defects]
- Equipment Most Affected: [list]

## Priority Recommendations
1. [Highest priority action]
2. [Second priority action]
3. [Third priority action]

## Prevention Strategy
(Long-term actions to prevent recurrence)
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=2048,
        )
        return {
            "summary": response.content,
            "model": response.model,
            "report_type": "rca",
        }

    def summarize_ct_efficiency_report(
        self, report_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate executive summary of CT Efficiency analysis report."""
        prompt = f"""Analyze this Cycle Time Efficiency report and provide an executive summary:

{json.dumps(report_data, indent=2, default=str)}

Structure your response as:

## Executive Summary
(2-3 sentence overview of efficiency findings)

## Overall Efficiency
- Average Efficiency Score: [value]
- Performance Tier: [Top/High/Medium/Low/Poor]

## Supplier Rankings
(Top 3 and bottom 3 suppliers with scores)

## Equipment Performance
- Most Efficient: [equipment list]
- Needs Improvement: [equipment list]

## Consistency Analysis
- Most Consistent: [tools/equipment]
- High Variability: [tools/equipment]

## Recommendations
1. [Action for low performers]
2. [Action for variability reduction]
3. [Best practice sharing from top performers]
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=2048,
        )
        return {
            "summary": response.content,
            "model": response.model,
            "report_type": "ct_efficiency",
        }

    def summarize_ct_deviation_report(
        self, report_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate executive summary of CT Deviation analysis report."""
        prompt = f"""Analyze this Cycle Time Deviation report and provide an executive summary:

{json.dumps(report_data, indent=2, default=str)}

Structure your response as:

## Executive Summary
(2-3 sentence overview of deviation findings)

## Deviation Overview
- Average Deviation: [%]
- Shots On-Target: [%]
- Shots Above Target: [%]
- Shots Below Target: [%]

## Performance Categories
- Excellent (<2% deviation): [count]
- Good (2-5%): [count]
- Acceptable (5-10%): [count]
- Poor (10-15%): [count]
- Critical (>15%): [count]

## Problem Areas
(Equipment/tools with highest deviation)

## Recommendations
1. [Address critical deviations]
2. [Process adjustments needed]
3. [Monitoring improvements]
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=2048,
        )
        return {
            "summary": response.content,
            "model": response.model,
            "report_type": "ct_deviation",
        }

    def summarize_tooling_eol_report(
        self, report_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate executive summary of Tooling EOL (End-of-Life) prediction report."""
        prompt = f"""Analyze this Tooling End-of-Life (EOL) prediction report and provide an executive summary:

{json.dumps(report_data, indent=2, default=str)}

Structure your response as:

## Executive Summary
(2-3 sentence overview of EOL predictions)

## Critical Alerts (Immediate Action Required)
(Tools/molds approaching EOL within 30 days or overutilized)

## Upcoming Replacements (30-90 days)
(Tools needing replacement soon)

## Utilization Analysis
- Overutilized: [list with %]
- Optimal Utilization: [list]
- Underutilized: [list]

## Confidence Assessment
(Reliability of predictions - high/medium/low confidence items)

## Recommended Actions
1. [Immediate replacements]
2. [Preventive maintenance scheduling]
3. [Budget planning for replacements]

## Cost Planning
(Estimated replacement costs if available)
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=2048,
        )
        return {
            "summary": response.content,
            "model": response.model,
            "report_type": "tooling_eol",
        }

    def summarize_capacity_report(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary of Capacity/OEE analysis report."""
        prompt = f"""Analyze this Capacity/OEE (Overall Equipment Effectiveness) report and provide an executive summary:

{json.dumps(report_data, indent=2, default=str)}

Structure your response as:

## Executive Summary
(2-3 sentence overview of capacity and OEE findings)

## OEE Breakdown
- Overall OEE: [%]
- Availability: [%] - (impact of downtime)
- Performance: [%] - (impact of slow cycles)
- Quality: [%] - (impact of defects)

## Capacity Utilization
- Current Production: [units]
- Optimal Capacity: [units]
- Utilization Rate: [%]
- Gap to Optimal: [units]

## Bottlenecks Identified
(Equipment/processes limiting throughput)

## Improvement Opportunities
- If Availability improved to [target]: [potential gain]
- If Performance improved to [target]: [potential gain]
- If Quality improved to [target]: [potential gain]

## Recommendations
1. [Address biggest OEE factor]
2. [Bottleneck resolution]
3. [Capacity expansion considerations]
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=2048,
        )
        return {
            "summary": response.content,
            "model": response.model,
            "report_type": "capacity",
        }

    def summarize_any_report(
        self,
        report_type: str,
        report_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Summarize any analysis report based on type.

        Args:
            report_type: Type of report (roi, runrate, rca, ct_efficiency, ct_deviation, tooling_eol, capacity, risk_tower)
            report_data: Report data to summarize

        Returns:
            Summary with key findings and recommendations
        """
        report_type_lower = report_type.lower().replace("-", "_").replace(" ", "_")

        summarizers = {
            "roi": self.summarize_roi_report,
            "runrate": self.summarize_runrate_report,
            "run_rate": self.summarize_runrate_report,
            "rca": self.summarize_rca_report,
            "root_cause": self.summarize_rca_report,
            "ct_efficiency": self.summarize_ct_efficiency_report,
            "ctefficiency": self.summarize_ct_efficiency_report,
            "efficiency": self.summarize_ct_efficiency_report,
            "ct_deviation": self.summarize_ct_deviation_report,
            "ctdeviation": self.summarize_ct_deviation_report,
            "deviation": self.summarize_ct_deviation_report,
            "tooling_eol": self.summarize_tooling_eol_report,
            "eol": self.summarize_tooling_eol_report,
            "end_of_life": self.summarize_tooling_eol_report,
            "capacity": self.summarize_capacity_report,
            "oee": self.summarize_capacity_report,
            "risk_tower": self.summarize_risk_tower,
            "risktower": self.summarize_risk_tower,
        }

        summarizer = summarizers.get(report_type_lower)
        if summarizer:
            # Special handling for risk_tower which expects a list
            if report_type_lower in ("risk_tower", "risktower"):
                if isinstance(report_data, dict):
                    data = report_data.get("equipment", [report_data])
                else:
                    data = report_data
                return summarizer(data)
            return summarizer(report_data)
        else:
            # Generic summarization for unknown report types
            return self._summarize_generic_report(report_type, report_data)

    def _summarize_generic_report(
        self,
        report_type: str,
        report_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generic summarization for any report type."""
        prompt = f"""Analyze this {report_type} report and provide an executive summary:

{json.dumps(report_data, indent=2, default=str)}

Structure your response as:

## Executive Summary
(2-3 sentence overview)

## Key Metrics
(Important numbers and their meaning)

## Key Findings
(Top 3-5 insights from the data)

## Concerns
(Any metrics outside acceptable ranges)

## Recommendations
(Specific actions to improve performance)
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            use_case="reasoning",
            max_tokens=2048,
        )
        return {
            "summary": response.content,
            "model": response.model,
            "report_type": report_type,
        }

    def clear_conversation(self, session_id: str) -> bool:
        """Clear conversation history."""
        if session_id in self.conversations:
            del self.conversations[session_id]
            logger.info(f"Cleared conversation: {session_id}")
            return True
        return False


# Singleton instance
chat_assistant = ManufacturingChatAssistant()
