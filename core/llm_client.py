"""
LLM Client for interacting with AWS Bedrock (Claude).

Handles all LLM-related operations including message formatting,
API calls, and response processing.
"""

import os
from typing import Any, Dict, List, Optional

import boto3

from .prompts import get_system_prompt
from .token_tracker import get_token_tracker


class BedrockClient:
    """Client for AWS Bedrock Claude interactions."""

    def __init__(self, region_name: str = None):
        """
        Initialize Bedrock client.

        Args:
            region_name: AWS region for Bedrock (defaults to env vars)
        """
        # Get region from environment or use provided/default
        if region_name is None:
            region_name = os.getenv("BEDROCK_REGION") or os.getenv(
                "AWS_DEFAULT_REGION", "us-east-1"
            )

        # Get model ID from environment or use default
        self.model_id = os.getenv(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
        )

        # Get bearer token if available (for Bedrock Marketplace/cross-region access)
        bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")

        # Initialize Bedrock client
        try:
            if bearer_token:
                # Use bearer token authentication (requires custom endpoint)
                # Decode the bearer token to extract credentials
                import base64

                try:
                    # Bearer token format: "ABSKQmVkcm9ja0FQSUtleS0..."
                    # This is a base64-encoded access key
                    decoded = base64.b64decode(bearer_token.replace("ABSK", ""))
                    token_str = decoded.decode("utf-8")

                    # Parse the token (format: accessKey:secretPart)
                    if ":" in token_str:
                        access_key, secret_part = token_str.split(":", 1)
                        self.bedrock = boto3.client(
                            "bedrock-runtime",
                            region_name=region_name,
                            aws_access_key_id=f"ABSK{access_key}",
                            aws_secret_access_key=secret_part,
                        )
                    else:
                        # If parsing fails, try as direct bearer token
                        self.bedrock = boto3.client(
                            "bedrock-runtime",
                            region_name=region_name,
                            aws_access_key_id=bearer_token,
                        )
                except Exception as e:
                    print(f"⚠️  Bearer token decode failed: {e}")
                    # Fallback to standard credentials
                    self.bedrock = boto3.client(
                        "bedrock-runtime", region_name=region_name
                    )
            else:
                # Use default AWS credentials (from ~/.aws/credentials or IAM role)
                self.bedrock = boto3.client("bedrock-runtime", region_name=region_name)

            print(
                f"✅ Bedrock client initialized: region={region_name}, model={self.model_id}"
            )
        except Exception as e:
            print(f"❌ Failed to initialize Bedrock client: {e}")
            raise

    def get_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        session_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """
        Get response from Claude via AWS Bedrock.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool definitions
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            session_id: Session identifier for tracking

        Returns:
            Response dictionary or None on error
        """
        try:
            # Build request parameters with prompt caching
            # System prompt is >1024 tokens, so we enable caching for cost/speed benefits
            # Note: AWS Bedrock uses 'cachePoint' for prompt caching
            request_params = {
                "modelId": self.model_id,
                "messages": messages,
                "inferenceConfig": {
                    "maxTokens": max_tokens,
                    "temperature": temperature,
                },
                "system": [
                    {
                        "text": get_system_prompt(),
                    },
                    {"cachePoint": {"type": "default"}},  # Enable prompt caching
                ],
            }

            # Add tools if provided
            if tools:
                request_params["toolConfig"] = {"tools": tools}

            # Call Bedrock API
            response = self.bedrock.converse(**request_params)

            # Track token usage
            try:
                tracker = get_token_tracker()
                tracker.track_bedrock_response(
                    response,
                    operation="chat_interface",
                    session_id=session_id,
                )
            except Exception:
                # Don't let tracking errors break the chat
                pass

            return response

        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            print(f"❌ Error calling Bedrock: {e}")
            print(f"Model ID: {self.model_id}")
            print(f"Error details:\n{error_details}")
            return None


def format_tool_result(
    tool_use_id: str, result: Dict[str, Any], is_error: bool = False
) -> Dict[str, Any]:
    """
    Format tool result for Claude.

    Args:
        tool_use_id: ID of the tool use
        result: Tool execution result
        is_error: Whether this is an error result

    Returns:
        Formatted tool result message
    """

    return {
        "role": "user",
        "content": [
            {
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "content": [
                        {
                            "json": {
                                "error": str(result) if is_error else None,
                                "result": result if not is_error else None,
                            }
                        }
                    ],
                    "status": "error" if is_error else "success",
                }
            }
        ],
    }


def extract_text_from_response(response: Dict[str, Any]) -> str:
    """
    Extract text content from Claude's response.

    Args:
        response: Bedrock API response

    Returns:
        Extracted text content
    """
    try:
        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])

        text_parts = []
        for block in content_blocks:
            if "text" in block:
                text_parts.append(block["text"])

        return "\n\n".join(text_parts) if text_parts else ""
    except Exception as e:
        print(f"Error extracting text: {e}")
        return ""


def extract_tool_uses(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract tool use requests from Claude's response.

    Args:
        response: Bedrock API response

    Returns:
        List of tool use dictionaries
    """
    try:
        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])

        tool_uses = []
        for block in content_blocks:
            if "toolUse" in block:
                tool_uses.append(block["toolUse"])

        return tool_uses
    except Exception as e:
        print(f"Error extracting tool uses: {e}")
        return []


def get_stop_reason(response: Dict[str, Any]) -> str:
    """
    Get the stop reason from response.

    Args:
        response: Bedrock API response

    Returns:
        Stop reason string
    """
    try:
        return response.get("stopReason", "")
    except Exception:
        return ""
