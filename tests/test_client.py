"""Tests for Smart Oil Gauge API Client."""

import json

import aiohttp
import pytest
from aresponses import ResponsesMockServer

from custom_components.smart_oil_gauge.client import (
    CannotConnect,
    InvalidAuth,
    SmartOilGaugeClient,
    SmartOilGaugeException,
)

pytestmark = pytest.mark.enable_socket

LOGIN_HTML_SUCCESS = """
<!doctype html>
<html>
<body>
    <form method="post">
        <input type="hidden" name="ccf_nonce" value="test_nonce_value" />
    </form>
</body>
</html>
"""

LOGIN_HTML_ERROR = """
<!doctype html>
<html>
<body>
    <form method="post">
        <p class="app_error">Invalid credentials</p>
        <input type="hidden" name="ccf_nonce" value="test_nonce_value" />
    </form>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_async_login_success(aresponses: ResponsesMockServer) -> None:
    """Test successful login sequence."""
    # Mock GET login page
    aresponses.add(
        "app.smartoilgauge.com",
        "/login.php",
        "GET",
        aresponses.Response(text=LOGIN_HTML_SUCCESS, status=200),
    )
    # Mock POST login submission returning a 302 Redirect to app.php
    aresponses.add(
        "app.smartoilgauge.com",
        "/login.php",
        "POST",
        aresponses.Response(
            status=302,
            headers={"Location": "https://app.smartoilgauge.com/app.php"},
        ),
    )
    # Mock GET app.php landing page after redirect
    aresponses.add(
        "app.smartoilgauge.com",
        "/app.php",
        "GET",
        aresponses.Response(text="Welcome to the dashboard", status=200),
    )

    async with aiohttp.ClientSession() as session:
        client = SmartOilGaugeClient(session, "test@example.com", "password")
        assert await client.async_login() is True


@pytest.mark.asyncio
async def test_async_login_invalid_credentials(aresponses: ResponsesMockServer) -> None:
    """Test login failure due to invalid credentials."""
    aresponses.add(
        "app.smartoilgauge.com",
        "/login.php",
        "GET",
        aresponses.Response(text=LOGIN_HTML_SUCCESS, status=200),
    )
    # Return HTML containing app_error (remains on login.php)
    aresponses.add(
        "app.smartoilgauge.com",
        "/login.php",
        "POST",
        aresponses.Response(
            text=LOGIN_HTML_ERROR,
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        client = SmartOilGaugeClient(session, "test@example.com", "wrong")
        with pytest.raises(InvalidAuth):
            await client.async_login()


@pytest.mark.asyncio
async def test_async_login_cannot_connect(aresponses: ResponsesMockServer) -> None:
    """Test login failure due to connection error."""
    aresponses.add(
        "app.smartoilgauge.com",
        "/login.php",
        "GET",
        aresponses.Response(status=500),
    )

    async with aiohttp.ClientSession() as session:
        client = SmartOilGaugeClient(session, "test@example.com", "password")
        with pytest.raises(CannotConnect):
            await client.async_login()


@pytest.mark.asyncio
async def test_async_get_tanks_success(aresponses: ResponsesMockServer) -> None:
    """Test successful retrieval of tanks list."""
    mock_tanks_response = {
        "result": "ok",
        "tanks": [
            {
                "tank_id": "12345",
                "tank_name": "Test Tank",
                "sensor_gallons": "150.5",
                "nominal": "275",
                "battery": "Good",
                "sensor_usg": "1.2",
            }
        ],
    }

    aresponses.add(
        "app.smartoilgauge.com",
        "/ajax/main_ajax.php",
        "POST",
        aresponses.Response(
            text=json.dumps(mock_tanks_response),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        client = SmartOilGaugeClient(session, "test@example.com", "password")
        # Pre-populate session cookie to simulate logged-in state
        client._session.cookie_jar.update_cookies({"PHPSESSID": "test_session_id"})
        tanks = await client.async_get_tanks()
        assert len(tanks) == 1
        assert tanks[0]["tank_name"] == "Test Tank"
        assert tanks[0]["sensor_gallons"] == "150.5"


@pytest.mark.asyncio
async def test_async_get_tanks_session_expiry_relogin(
    aresponses: ResponsesMockServer,
) -> None:
    """Test auto-relogin when session is expired (Access Denied)."""
    # 1. Return Access Denied error on first fetch
    aresponses.add(
        "app.smartoilgauge.com",
        "/ajax/main_ajax.php",
        "POST",
        aresponses.Response(
            text=json.dumps({"result": "error", "message": "Access Denied"}),
            content_type="application/json",
            status=200,
        ),
    )
    # 2. Mock login sequence (GET + POST + GET app.php)
    aresponses.add(
        "app.smartoilgauge.com",
        "/login.php",
        "GET",
        aresponses.Response(text=LOGIN_HTML_SUCCESS, status=200),
    )
    aresponses.add(
        "app.smartoilgauge.com",
        "/login.php",
        "POST",
        aresponses.Response(
            status=302,
            headers={"Location": "https://app.smartoilgauge.com/app.php"},
        ),
    )
    aresponses.add(
        "app.smartoilgauge.com",
        "/app.php",
        "GET",
        aresponses.Response(text="Welcome", status=200),
    )
    # 3. Return successful tank list on retry
    mock_tanks_response = {
        "result": "ok",
        "tanks": [{"tank_id": "12345", "tank_name": "Test Tank"}],
    }
    aresponses.add(
        "app.smartoilgauge.com",
        "/ajax/main_ajax.php",
        "POST",
        aresponses.Response(
            text=json.dumps(mock_tanks_response),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        client = SmartOilGaugeClient(session, "test@example.com", "password")
        # Pre-populate session cookie to simulate expired logged-in state
        client._session.cookie_jar.update_cookies({"PHPSESSID": "expired_session_id"})
        tanks = await client.async_get_tanks()
        assert len(tanks) == 1
        assert tanks[0]["tank_id"] == "12345"


@pytest.mark.asyncio
async def test_async_get_tanks_server_error(aresponses: ResponsesMockServer) -> None:
    """Test handling of generic server error from AJAX."""
    aresponses.add(
        "app.smartoilgauge.com",
        "/ajax/main_ajax.php",
        "POST",
        aresponses.Response(
            text=json.dumps({"result": "error", "message": "Database error"}),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        client = SmartOilGaugeClient(session, "test@example.com", "password")
        with pytest.raises(SmartOilGaugeException):
            await client.async_get_tanks()
