"""Fixtures for Smart Oil Gauge integration testing."""

from unittest.mock import patch

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in Home Assistant tests."""
    yield


SENSOR_CONFIG_HTML = """
<form method="post">
  <input type="hidden" name="registration_id" value="71796">
  <input type="hidden" name="ccf_nonce" value="abc123">
  <input type="text" name="description" value="My Tank">
  <select name="upload_interval">
    <option value="1">1</option><option value="6">6</option>
    <option value="12" selected>12</option><option value="24">24</option>
  </select>
  <input type="radio" name="tank_size" value="275">
  <input type="radio" name="tank_size" value="550" checked>
  <input type="tel" value="">
  <input type="number" name="offset_inches" value="0">
  <select name="num_tanks"><option value="1">1</option>
    <option value="2" selected>2</option></select>
  <input type="submit" name="submit" value="Save">
</form>
"""


@pytest.fixture(autouse=True)
def mock_sensor_config(request):
    """Serve a Sensor Config page instead of calling the portal."""
    from custom_components.smart_oil_gauge.client import parse_sensor_config

    if request.node.get_closest_marker("real_sensor_config"):
        yield None
        return
    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_sensor_config",
        return_value=parse_sensor_config(SENSOR_CONFIG_HTML),
    ) as mock:
        yield mock
