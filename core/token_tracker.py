"""
Token Usage Tracking System

Centralized token usage tracking for AWS Bedrock and LLM services.
Tracks input/output tokens and estimates costs.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Represents a single token usage record."""

    timestamp: str
    model_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    operation: str
    session_id: str


class TokenTracker:
    """Centralized token usage tracker."""

    def __init__(self):
        self.usage_records: List[TokenUsage] = []
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Pricing data (per 1M tokens)
        self.pricing = {
            "claude-3-7-sonnet": {"input": 3.0, "output": 15.0},
            "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
            "claude-3-haiku": {"input": 0.25, "output": 1.25},
        }

    def reset_session(self):
        """Reset the current session."""
        self.usage_records = []
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def track_usage(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        operation: str = "unknown",
        session_id: Optional[str] = None,
    ) -> TokenUsage:
        """Track token usage for a single operation."""

        total_tokens = input_tokens + output_tokens

        # Calculate estimated cost
        model_pricing = self.pricing.get(model_id, self.pricing["claude-3-7-sonnet"])
        input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
        estimated_cost = input_cost + output_cost

        usage = TokenUsage(
            timestamp=datetime.now().isoformat(),
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            operation=operation,
            session_id=session_id or self.session_id,
        )

        self.usage_records.append(usage)

        logger.info(
            f"Tracked {total_tokens} tokens for {operation}: ${estimated_cost:.4f}"
        )

        return usage

    def track_bedrock_response(
        self,
        response: Dict,
        operation: str = "bedrock_call",
        session_id: Optional[str] = None,
    ) -> TokenUsage:
        """Track token usage from AWS Bedrock response."""

        # Extract token usage from Bedrock response
        usage_info = response.get("usage", {})
        input_tokens = usage_info.get("inputTokens", 0)
        output_tokens = usage_info.get("outputTokens", 0)

        # Get model ID from response
        model_id = response.get("modelId", "claude-3-7-sonnet")

        return self.track_usage(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            operation=operation,
            session_id=session_id,
        )

    def track_langchain_response(
        self,
        response: Dict,
        operation: str = "langchain_call",
        session_id: Optional[str] = None,
    ) -> TokenUsage:
        """Track token usage from LangChain response."""

        # Extract token usage from LangChain response
        usage_info = response.get("usage_metadata", {})
        input_tokens = usage_info.get("input_tokens", 0)
        output_tokens = usage_info.get("output_tokens", 0)

        # Get model ID from response
        model_id = response.get("model", "claude-3-7-sonnet")

        return self.track_usage(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            operation=operation,
            session_id=session_id,
        )

    def get_session_summary(self, session_id: Optional[str] = None) -> Dict:
        """Get summary of token usage for a session."""

        target_session = session_id or self.session_id
        session_records = [
            r for r in self.usage_records if r.session_id == target_session
        ]

        if not session_records:
            return {
                "session_id": target_session,
                "total_operations": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "operations": [],
            }

        total_input = sum(r.input_tokens for r in session_records)
        total_output = sum(r.output_tokens for r in session_records)
        total_tokens = sum(r.total_tokens for r in session_records)
        total_cost = sum(r.estimated_cost for r in session_records)

        return {
            "session_id": target_session,
            "total_operations": len(session_records),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "operations": [asdict(r) for r in session_records],
        }

    def save_to_file(self, filepath: str):
        """Save usage records to JSON file."""
        data = {
            "session_id": self.session_id,
            "records": [asdict(r) for r in self.usage_records],
            "summary": self.get_session_summary(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Token usage saved to {filepath}")


# Global tracker instance
_tracker_instance: Optional[TokenTracker] = None


def get_token_tracker() -> TokenTracker:
    """Get the global token tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = TokenTracker()
    return _tracker_instance
