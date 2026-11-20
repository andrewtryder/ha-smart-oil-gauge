"""Tests for the client's hourly-history endpoints."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.smart_oil_gauge.client import (
    EXPORT_URL,
    CannotConnect,
    SmartOilGaugeClient,
    SmartOilGaugeException,
)

CSV = 'Time,Gallons\n"2026-11-16 00:51:31",65.62\n'


class Resp:
    """Minimal aiohttp response stand-in."""

    def __init__(self, *, status=200, text="", data=None, json_error=None):
        """Initialize."""
        self.status = status
        self.headers: dict[str, str] = {}
        self._text = text
        self._data = data
        self._json_error = json_error

    async def __aenter__(self):
        """Enter."""
        return self

    async def __aexit__(self, *args):
        """Exit."""

    async def text(self):
        """Return text."""
        return self._text

    async def json(self, **kwargs):
        """Return JSON."""
        if self._json_error:
            raise self._json_error
        return self._data


def _client(*responses) -> tuple[SmartOilGaugeClient, MagicMock]:
    session = MagicMock()
    session.post = MagicMock(side_effect=list(responses))
    client = SmartOilGaugeClient(session, "u", "p")
    client.async_login = AsyncMock(return_value=True)
    return client, session


async def test_graph_data_success() -> None:
    """Graph data is posted with the tank and data server."""
    client, session = _client(Resp(data={"result": "ok", "datasets": {}}))
    data = await client.async_get_graph_data("940670", "data.example.com")
    assert data["result"] == "ok"
    sent = session.post.call_args.kwargs["data"]
    assert sent == {
        "action": "get_graph_data",
        "tank_id": "940670",
        "data_servers": "data.example.com",
    }


async def test_graph_data_relogin_on_403_and_access_denied() -> None:
    """Expired sessions trigger exactly one login retry."""
    client, _ = _client(Resp(status=403), Resp(data={"result": "ok"}))
    assert (await client.async_get_graph_data("1", "d"))["result"] == "ok"
    assert client.async_login.await_count == 1

    client, _ = _client(
        Resp(data={"result": "error", "message": "Access Denied"}),
        Resp(data={"result": "ok"}),
    )
    assert (await client.async_get_graph_data("1", "d"))["result"] == "ok"

    client, _ = _client(Resp(data={"result": "error", "message": "nope"}))
    with pytest.raises(SmartOilGaugeException):
        await client.async_get_graph_data("1", "d")


@pytest.mark.parametrize(
    ("resp", "error"),
    [
        (Resp(json_error=json.JSONDecodeError("x", "y", 0)), CannotConnect),
        (Resp(status=500), CannotConnect),
        (TimeoutError(), CannotConnect),
        (aiohttp.ClientError(), CannotConnect),
    ],
)
async def test_graph_data_errors(resp, error) -> None:
    """Transport and decoding errors become CannotConnect."""
    client, _ = _client(resp)
    with pytest.raises(error):
        await client.async_get_graph_data("1", "d")


async def test_export_history_success() -> None:
    """The export posts the registration and date range and returns CSV."""
    client, session = _client(Resp(text=CSV))
    text = await client.async_export_history(
        "71796", date(2026, 11, 16), date(2026, 11, 17)
    )
    assert text == CSV
    call = session.post.call_args
    assert call.args[0] == EXPORT_URL
    assert call.kwargs["params"] == {"registration_id": "71796"}
    assert call.kwargs["data"] == {
        "registration_id": "71796",
        "startdate": "2026-11-16",
        "enddate": "2026-11-17",
    }


async def test_export_history_relogin() -> None:
    """A login page or 401 triggers one login retry; then it gives up."""
    client, _ = _client(Resp(text="<html>login</html>"), Resp(text=CSV))
    assert await client.async_export_history("1", date.today(), date.today()) == CSV

    client, _ = _client(Resp(status=401), Resp(text=CSV))
    assert await client.async_export_history("1", date.today(), date.today()) == CSV

    client, _ = _client(Resp(text="<html>"), Resp(text="<html>"))
    with pytest.raises(SmartOilGaugeException):
        await client.async_export_history("1", date.today(), date.today())


@pytest.mark.parametrize("exc", [TimeoutError(), aiohttp.ClientError()])
async def test_export_history_errors(exc) -> None:
    """Transport errors become CannotConnect."""
    client, _ = _client(exc)
    with pytest.raises(CannotConnect):
        await client.async_export_history("1", date.today(), date.today())
