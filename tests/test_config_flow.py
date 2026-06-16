"""Tests for Smart Oil Gauge config flow."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.smart_oil_gauge.client import CannotConnect, InvalidAuth
from custom_components.smart_oil_gauge.const import DOMAIN


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
        return_value={"title": "Smart Oil Gauge (user@example.com)"},
    ) as mock_validate:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "password123",
            },
        )
        await hass.async_block_till_done()

        assert len(mock_validate.mock_calls) == 1
        assert result2["type"] is FlowResultType.CREATE_ENTRY
        assert result2["title"] == "Smart Oil Gauge (user@example.com)"
        assert result2["data"] == {
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "password123",
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
            },
        )
        await hass.async_block_till_done()

        assert result2["type"] is FlowResultType.FORM
        assert result2["errors"] == {"base": "unknown"}
