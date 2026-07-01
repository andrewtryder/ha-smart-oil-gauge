"""Tests for Smart Oil Gauge API Client."""

from unittest.mock import MagicMock

import aiohttp
import pytest

from custom_components.smart_oil_gauge.client import (
    CannotConnect,
    InvalidAuth,
    SmartOilGaugeClient,
    SmartOilGaugeException,
)

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


class MockResponse:
    """Mock aiohttp response."""

    def __init__(self, text="", json_data=None, status=200, url=""):
        """Initialize."""
        self._text = text
        self._json_data = json_data
        self.status = status
        self.url = url
        self.headers = {}

    async def __aenter__(self):
        """Enter."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit."""
        pass

    async def text(self):
        """Return text."""
        return self._text

    async def json(self):
        """Return json."""
        return self._json_data


class MockCookieJar:
    """Mock CookieJar."""

    def __init__(self):
        """Initialize."""
        self._cookies = {}

    def update_cookies(self, cookies):
        """Update cookies."""
        self._cookies.update(cookies)

    def __iter__(self):
        """Iterate cookies."""
        from types import SimpleNamespace

        for k, v in self._cookies.items():
            yield SimpleNamespace(key=k, value=v)


@pytest.fixture
def mock_session():
    """Mock aiohttp.ClientSession."""
    session = MagicMock(spec=aiohttp.ClientSession)
    session.cookie_jar = MockCookieJar()
    return session


@pytest.mark.asyncio
async def test_async_login_success(mock_session) -> None:
    """Test successful login sequence."""
    client = SmartOilGaugeClient(mock_session, "test@example.com", "password")

    # Mock GET login page
    mock_session.get.return_value = MockResponse(text=LOGIN_HTML_SUCCESS, status=200)

    # Mock POST login submission returning a 302 Redirect to app.php
    # Client expects r_login.url to be the redirected url "app.php"
    post_response = MockResponse(
        status=200, url="https://app.smartoilgauge.com/app.php"
    )
    mock_session.post.return_value = post_response

    assert await client.async_login() is True


@pytest.mark.asyncio
async def test_async_login_invalid_credentials(mock_session) -> None:
    """Test login failure due to invalid credentials."""
    client = SmartOilGaugeClient(mock_session, "test@example.com", "wrong")

    mock_session.get.return_value = MockResponse(text=LOGIN_HTML_SUCCESS, status=200)

    # Return HTML containing app_error
    post_response = MockResponse(
        text=LOGIN_HTML_ERROR, status=200, url="https://app.smartoilgauge.com/login.php"
    )
    mock_session.post.return_value = post_response

    with pytest.raises(InvalidAuth):
        await client.async_login()


@pytest.mark.asyncio
async def test_async_login_cannot_connect(mock_session) -> None:
    """Test login failure due to connection error."""
    client = SmartOilGaugeClient(mock_session, "test@example.com", "password")

    mock_session.get.return_value = MockResponse(status=500)

    with pytest.raises(CannotConnect):
        await client.async_login()


@pytest.mark.asyncio
async def test_async_get_tanks_success(mock_session) -> None:
    """Test successful retrieval of tanks list."""
    client = SmartOilGaugeClient(mock_session, "test@example.com", "password")
    client._session.cookie_jar.update_cookies({"PHPSESSID": "test_session_id"})

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

    mock_session.post.return_value = MockResponse(
        json_data=mock_tanks_response, status=200
    )

    tanks = await client.async_get_tanks()
    assert len(tanks) == 1
    assert tanks[0]["tank_name"] == "Test Tank"
    assert tanks[0]["sensor_gallons"] == "150.5"


@pytest.mark.asyncio
async def test_async_get_tanks_session_expiry_relogin(mock_session) -> None:
    """Test auto-relogin when session is expired (Access Denied)."""
    client = SmartOilGaugeClient(mock_session, "test@example.com", "password")
    client._session.cookie_jar.update_cookies({"PHPSESSID": "expired_session_id"})

    # Setup sequence of responses for post:
    # 1. Access Denied
    # 2. Login POST redirect
    # 3. Successful tanks
    post_responses = [
        MockResponse(
            json_data={"result": "error", "message": "Access Denied"}, status=200
        ),
        MockResponse(status=200, url="https://app.smartoilgauge.com/app.php"),
        MockResponse(
            json_data={
                "result": "ok",
                "tanks": [{"tank_id": "12345", "tank_name": "Test Tank"}],
            },
            status=200,
        ),
    ]
    mock_session.post.side_effect = post_responses
    mock_session.get.return_value = MockResponse(text=LOGIN_HTML_SUCCESS, status=200)

    tanks = await client.async_get_tanks()
    assert len(tanks) == 1
    assert tanks[0]["tank_id"] == "12345"


@pytest.mark.asyncio
async def test_async_get_tanks_server_error(mock_session) -> None:
    """Test handling of generic server error from AJAX."""
    client = SmartOilGaugeClient(mock_session, "test@example.com", "password")
    client._session.cookie_jar.update_cookies({"PHPSESSID": "test_session_id"})

    mock_session.post.return_value = MockResponse(
        json_data={"result": "error", "message": "Database error"}, status=200
    )

    with pytest.raises(SmartOilGaugeException):
        await client.async_get_tanks()
