"""
Autonomous workflow agent package.

Holds the headless sense-reason-act controller and its decision trail, which
run on a trigger rather than a human chat turn. Re-exports the trail recorder
so callers do not need to know the module layout.
"""

from .trail_recorder import TrailRecorder, TrailRecorderError, load_trail

__all__ = [
    "TrailRecorder",
    "TrailRecorderError",
    "load_trail",
]
