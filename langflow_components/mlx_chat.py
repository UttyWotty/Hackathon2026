"""
Custom Langflow component for local MLX LLM inference with Langfuse tracing.
Connects to an MLX server via the OpenAI-compatible API and logs prompts/responses to Langfuse.
Appears in Langflow sidebar under its own category.
"""

import os
from typing import Optional

from langfuse import Langfuse
from lfx.custom.custom_component.component import Component
from lfx.io import FloatInput, IntInput, MessageTextInput, Output, StrInput
from lfx.schema.message import Message
from openai import OpenAI

LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")


def _get_langfuse_client() -> Optional[Langfuse]:
    """Return a Langfuse client if keys are configured, else None."""
    if not LANGFUSE_SECRET_KEY or not LANGFUSE_PUBLIC_KEY:
        return None
    return Langfuse(
        secret_key=LANGFUSE_SECRET_KEY,
        public_key=LANGFUSE_PUBLIC_KEY,
        host=LANGFUSE_HOST,
    )


class MLXChat(Component):
    display_name = "MLX Local LLM"
    description = (
        "Chat with a local MLX server via OpenAI-compatible API. Traces to Langfuse."
    )
    icon = "bot"
    name = "MLXChat"

    inputs = [
        MessageTextInput(
            name="input_value",
            display_name="Input",
            required=True,
            tool_mode=True,
        ),
        StrInput(
            name="system_message",
            display_name="System Message",
            value="You are a helpful manufacturing analytics assistant.",
        ),
        StrInput(
            name="base_url",
            display_name="MLX Server URL",
            value="http://host.docker.internal:8081/v1",
        ),
        StrInput(
            name="model_name",
            display_name="Model Name",
            value="mlx-community/Qwen3-32B-4bit",
        ),
        FloatInput(
            name="temperature",
            display_name="Temperature",
            value=0.7,
        ),
        IntInput(
            name="max_tokens",
            display_name="Max Tokens",
            value=2048,
            info="Maximum number of tokens in the response.",
        ),
    ]

    outputs = [
        Output(display_name="Response", name="response", method="run_chat"),
    ]

    def run_chat(self) -> Message:
        """Run chat completion and trace the prompt/response to Langfuse."""
        client = OpenAI(base_url=self.base_url, api_key="not-needed")
        messages = []
        if self.system_message:
            messages.append({"role": "system", "content": self.system_message})
        messages.append({"role": "user", "content": str(self.input_value)})

        response = client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        text = response.choices[0].message.content

        usage = response.usage
        self._trace_to_langfuse(messages, text, usage)

        return Message(text=text)

    def _trace_to_langfuse(
        self,
        messages: list[dict[str, str]],
        output: str,
        usage: object,
    ) -> None:
        """Send the prompt, response, and token usage to Langfuse."""
        langfuse = _get_langfuse_client()
        if langfuse is None:
            return

        trace = langfuse.trace(
            name="mlx-chat",
            metadata={"model": self.model_name, "temperature": self.temperature},
        )
        trace.generation(
            name="mlx-completion",
            model=self.model_name,
            input=messages,
            output=output,
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            },
            metadata={"temperature": self.temperature},
        )
        langfuse.flush()
