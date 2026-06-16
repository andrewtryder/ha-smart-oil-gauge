"""Tests for Smart Oil Gauge config flow."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_oil_gauge.client import CannotConnect, InvalidAuth
from custom_components.smart_oil_gauge.config_flow import validate_input
from custom_components.smart_oil_gauge.const import CONF_UPDATE_INTERVAL_HOURS, DOMAIN


async def test_flow_user_init(hass: HomeAssistant) -> None:
    """Test user step form is presented."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_flow_user_success(hass: HomeAssistant) -> None:
    """Test successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.smart_oil_gauge.config_flow.validate_input",
        return_value={"title": "House Tank"},
    ) as mock_validate:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "password123",
                CONF_UPDATE_INTERVAL_HOURS: 12,
            },
        )
        await hass.async_block_till_done()

        assert len(mock_validate.mock_calls) == 1
        assert result2["type"] is FlowResultType.CREATE_ENTRY
        assert result2["title"] == "House Tank"
        assert result2["data"] == {
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "password123",
            CONF_UPDATE_INTERVAL_HOURS: 12,
        }


async def test_flow_user_cannot_connect(hass: HomeAssistant) -> None:
    """Test connection error during validation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.smart_oil_gauge.config_flow.validate_input",
        side_effect=CannotConnect,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "password123",
                CONF_UPDATE_INTERVAL_HOURS: 6,
            },
        )
        await hass.async_block_till_done()

        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_flow_user_invalid_auth(hass: HomeAssistant) -> None:
    """Test authentication error during validation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.smart_oil_gauge.config_flow.validate_input",
        side_effect=InvalidAuth,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "password123",
                CONF_UPDATE_INTERVAL_HOURS: 6,
            },
        )
        await hass.async_block_till_done()

        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"] == {"base": "invalid_auth"}


async def test_flow_user_unknown_exception(hass: HomeAssistant) -> None:
    """Test unknown error during validation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.smart_oil_gauge.config_flow.validate_input",
        side_effect=Exception,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "password123",
                CONF_UPDATE_INTERVAL_HOURS: 6,
            },
        )
        await hass.async_block_till_done()

        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"] == {"base": "unknown"}


async def test_validate_input(hass: HomeAssistant) -> None:
    """Test validate_input helper."""
    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_login",
        return_value=True,
    ), patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=[{"tank_name": "House Tank"}],
    ):
        res = await validate_input(
            hass, {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "password"}
        )
        assert res == {"title": "House Tank"}

    with patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_login",
        return_value=True,
    ), patch(
        "custom_components.smart_oil_gauge.client.SmartOilGaugeClient.async_get_tanks",
        return_value=[],
    ):
        res = await validate_input(
            hass, {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "password"}
        )
        assert res == {"title": "Smart Oil Gauge"}


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "password123",
            CONF_UPDATE_INTERVAL_HOURS: 6,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_UPDATE_INTERVAL_HOURS: 12},
    )
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"] == {CONF_UPDATE_INTERVAL_HOURS: 12}
