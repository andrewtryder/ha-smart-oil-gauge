"""Tests for reading and changing the gauge's upload interval on the portal."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.smart_oil_gauge.client import (
    SENSOR_CONFIG_URL,
    CannotConnect,
    SmartOilGaugeClient,
    SmartOilGaugeException,
    parse_sensor_config,
)
from tests.conftest import SENSOR_CONFIG_HTML
from tests.test_client_history import Resp

pytestmark = pytest.mark.real_sensor_config


def _client(gets=(), posts=()) -> tuple[SmartOilGaugeClient, MagicMock]:
    session = MagicMock()
    session.get = MagicMock(side_effect=list(gets))
    session.post = MagicMock(side_effect=list(posts))
    client = SmartOilGaugeClient(session, "u", "p")
    client.async_login = AsyncMock(return_value=True)
    return client, session


def _page(interval: int = 12, **overrides: str) -> str:
    html = SENSOR_CONFIG_HTML.replace(
        '<option value="12" selected>12</option>', '<option value="12">12</option>'
    )
    html = html.replace(
        f'<option value="{interval}">', f'<option value="{interval}" selected>'
    )
    for old, new in overrides.items():
        html = html.replace(old, new)
    return html


def test_parse_sensor_config_like_a_browser() -> None:
    """Only the controls a browser would submit are collected."""
    config = parse_sensor_config(SENSOR_CONFIG_HTML)
    assert config is not None
    assert config.upload_interval == 12
    assert config.num_tanks == 2
    assert config.fields == [
        ("registration_id", "71796"),
        ("ccf_nonce", "abc123"),
        ("description", "My Tank"),
        ("upload_interval", "12"),
        ("tank_size", "550"),
        ("offset_inches", "0"),
        ("num_tanks", "2"),
    ]
    assert config.submit == ("submit", "Save")


def test_parse_sensor_config_edge_cases() -> None:
    """Pages without the form, and unusual controls, are handled."""
    assert parse_sensor_config("<html>login</html>") is None
    assert parse_sensor_config('<select name="upload_interval"></select>') is None
    html = """<form>
      <select name="upload_interval"><option>6</option></select>
      <select name="empty"></select>
      <textarea name="notes">hi</textarea>
      <input name="off" type="checkbox"><input name="on" type="checkbox" checked>
      <input name="x" disabled value="1"><input name="f" type="file">
      <input type="text" value="no name"><input name="b" type="button" value="b">
    </form>"""
    config = parse_sensor_config(html)
    assert config.fields == [("upload_interval", "6"), ("notes", "hi"), ("on", "on")]
    assert config.upload_interval == 6
    assert config.num_tanks is None
    assert config.submit is None


async def test_get_sensor_config_reads_page() -> None:
    """The page is loaded with the registration id; nothing is posted."""
    client, session = _client(gets=[Resp(text=SENSOR_CONFIG_HTML)])
    config = await client.async_get_sensor_config("71796")
    assert config.upload_interval == 12
    call = session.get.call_args
    assert call.args[0] == SENSOR_CONFIG_URL
    assert call.kwargs["params"] == {"registration_id": "71796"}
    session.post.assert_not_called()


async def test_get_sensor_config_relogin_and_errors() -> None:
    """Expired sessions log in once; other failures raise."""
    client, _ = _client(gets=[Resp(status=403), Resp(text=SENSOR_CONFIG_HTML)])
    assert (await client.async_get_sensor_config("1")).upload_interval == 12
    client, _ = _client(gets=[Resp(text="<html>"), Resp(text=SENSOR_CONFIG_HTML)])
    assert (await client.async_get_sensor_config("1")).upload_interval == 12
    client, _ = _client(gets=[Resp(text="<html>"), Resp(text="<html>")])
    with pytest.raises(SmartOilGaugeException):
        await client.async_get_sensor_config("1")
    for exc in (TimeoutError(), aiohttp.ClientError()):
        client, _ = _client(gets=[exc])
        with pytest.raises(CannotConnect):
            await client.async_get_sensor_config("1")


async def test_set_upload_interval_changes_only_the_interval() -> None:
    """The form is resubmitted unchanged except for the interval, then verified."""
    client, session = _client(
        gets=[Resp(text=_page(12)), Resp(text=_page(6, abc123="newnonce"))],
        posts=[Resp(text="ok")],
    )
    config = await client.async_set_upload_interval("71796", 6)
    assert config.upload_interval == 6
    sent = session.post.call_args.kwargs["data"]
    assert ("upload_interval", "6") in sent
    assert ("description", "My Tank") in sent
    assert ("tank_size", "550") in sent
    assert ("num_tanks", "2") in sent
    assert ("ccf_nonce", "abc123") in sent
    assert sent[-1] == ("submit", "Save")


async def test_set_upload_interval_detects_side_effects() -> None:
    """Any other field changing, or the interval not sticking, is an error."""
    client, _ = _client(
        gets=[
            Resp(text=_page(12)),
            Resp(text=_page(6, **{'value="My Tank"': 'value="Other"'})),
        ],
        posts=[Resp(text="ok")],
    )
    with pytest.raises(SmartOilGaugeException, match="description"):
        await client.async_set_upload_interval("71796", 6)

    client, _ = _client(
        gets=[Resp(text=_page(12)), Resp(text=_page(12))], posts=[Resp(text="ok")]
    )
    with pytest.raises(SmartOilGaugeException, match="is 12 after saving 6"):
        await client.async_set_upload_interval("71796", 6)

    client, _ = _client()
    with pytest.raises(ValueError):
        await client.async_set_upload_interval("71796", 25)

    for exc in (TimeoutError(), aiohttp.ClientError()):
        client, _ = _client(gets=[Resp(text=_page(12))], posts=[exc])
        with pytest.raises(CannotConnect):
            await client.async_set_upload_interval("71796", 6)
