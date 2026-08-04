"""Synthetic manufacturing dataset generator for the Snowflake Cortex hackathon build.

Generates a reproducible, client-free manufacturing dataset whose shape matches the
production DEMO_TABLE contract and whose planted defects are detectable by the
existing sense tools. Pure generation lives in the submodules; all I/O lives in loader and generate.
"""

from .dataset import Dataset, build_dataset, summarize
from .models import GenerationConfig, ProfileKind

__all__ = ["Dataset", "build_dataset", "summarize", "GenerationConfig", "ProfileKind"]
