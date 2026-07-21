"""
Custom Langflow component for local sentence-transformer embeddings.
Uses HuggingFace sentence-transformers to generate embeddings without external APIs.
Outputs a LangChain-compatible embeddings object for vector store components.
"""

from lfx.custom.custom_component.component import Component
from lfx.io import Output, StrInput
from lfx.schema.data import Data


class LocalEmbeddings(Component):
    display_name = "Local Embeddings"
    description = (
        "Generate embeddings locally using sentence-transformers (no API key needed)."
    )
    icon = "hash"
    name = "LocalEmbeddings"

    inputs = [
        StrInput(
            name="model_name",
            display_name="Model Name",
            value="all-MiniLM-L6-v2",
            info="HuggingFace model name for embeddings.",
        ),
    ]

    outputs = [
        Output(
            display_name="Embeddings",
            name="embeddings",
            method="build_embeddings",
        ),
    ]

    def build_embeddings(self) -> Data:
        from langchain_huggingface import HuggingFaceEmbeddings

        embeddings = HuggingFaceEmbeddings(model_name=self.model_name)
        return embeddings
