"""Tests for Smart Oil Gauge utility functions."""

import math

from custom_components.smart_oil_gauge.util import parse_finite_float


def test_parse_finite_float() -> None:
    """Test parse_finite_float with valid, invalid, and non-finite inputs."""
    assert parse_finite_float(10) == 10.0
    assert parse_finite_float(12.34) == 12.34
    assert parse_finite_float("150.5") == 150.5

    # Invalid / None
    assert parse_finite_float(None) is None
    assert parse_finite_float("invalid") is None
    assert parse_finite_float({}) is None

    # Non-finite values
    assert parse_finite_float("nan") is None
    assert parse_finite_float("inf") is None
    assert parse_finite_float("-inf") is None
    assert parse_finite_float(math.nan) is None
    assert parse_finite_float(math.inf) is None
    assert parse_finite_float(-math.inf) is None
