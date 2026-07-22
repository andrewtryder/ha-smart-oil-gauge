"""Utility functions for Smart Oil Gauge integration."""

from __future__ import annotations

import math
from typing import Any


def parse_finite_float(value: Any) -> float | None:
    """Parse a value to float, returning None if non-finite or invalid."""
    try:
        val = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return val if math.isfinite(val) else None
