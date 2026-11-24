"""Client module for the Smart Oil Gauge integration."""

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from .const import USER_AGENT

_LOGGER = logging.getLogger(__name__)

LOGIN_URL = "https://app.smartoilgauge.com/login.php"
AJAX_URL = "https://app.smartoilgauge.com/ajax/main_ajax.php"
EXPORT_URL = "https://app.smartoilgauge.com/export_data.php"
SENSOR_CONFIG_URL = "https://app.smartoilgauge.com/sensor_configuration.php"
NONCE_FIELD = "ccf_nonce"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
HISTORY_TIMEOUT = aiohttp.ClientTimeout(total=90)


class SmartOilGaugeException(Exception):
    """Base exception for Smart Oil Gauge integration."""


class CannotConnect(SmartOilGaugeException):
    """Exception to indicate connection error."""


class InvalidAuth(SmartOilGaugeException):
    """Exception to indicate authentication error."""


class SmartOilGaugeClient:
    """Client for reverse-engineered Smart Oil Gauge web app."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        """Initialize client."""
        self._session = session
        self.username = username
        self.password = password
        self._headers = {"User-Agent": USER_AGENT}

    async def async_close(self) -> None:
        """Close the client session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _async_fetch_login_nonce(self) -> str:
        """Fetch the login page and extract CSRF nonce."""
        _LOGGER.debug("Fetching login page to extract nonce")
        try:
            async with self._session.get(
                LOGIN_URL, headers=self._headers, timeout=REQUEST_TIMEOUT
            ) as r:
                self._check_http_status(r.status, r.headers.get("Retry-After"))
                html = await r.text()
        except TimeoutError as ex:
            _LOGGER.debug("Timeout error during login fetch: %s", ex)
            raise CannotConnect("Timeout connecting to portal") from ex
        except aiohttp.ClientError as ex:
            _LOGGER.debug("Connection error during login fetch: %s", ex)
            raise CannotConnect from ex

        soup = BeautifulSoup(html, "html.parser")
        nonce_input = soup.find("input", {"name": "ccf_nonce"})
        if not nonce_input or not nonce_input.get("value"):
            _LOGGER.debug("Could not find ccf_nonce on login page")
            raise CannotConnect("CSRF token ccf_nonce not found in page HTML")

        return str(nonce_input.get("value"))

    def _check_http_status(self, status: int, retry_after: str | None = None) -> None:
        """Check HTTP response status codes."""
        if status in (401, 403):
            raise InvalidAuth(f"Authentication failed with HTTP status {status}")
        if status == 429:
            _LOGGER.debug("Rate limited during request (Retry-After: %s)", retry_after)
            raise CannotConnect("Rate limit exceeded")
        if status >= 500:
            _LOGGER.debug("Server error during portal request: %s", status)
            raise CannotConnect("Server error from portal")
        if status != 200:
            _LOGGER.debug("Portal request returned unexpected status %s", status)
            raise CannotConnect(f"Failed portal request with status {status}")

    def _validate_login_html(self, login_html: str, final_url: str) -> None:
        """Validate login response HTML and final redirect URL."""
        if "app_error" in login_html:
            soup_err = BeautifulSoup(login_html, "html.parser")
            err_msg = soup_err.find(class_="app_error")
            if err_msg and err_msg.get_text(strip=True):
                error_text = err_msg.get_text(strip=True)
                _LOGGER.debug("Authentication failed with message: %s", error_text)
                raise InvalidAuth(error_text)

        if "app.php" not in final_url:
            _LOGGER.debug("Login redirect URL was not app.php: %s", final_url)
            raise InvalidAuth("Invalid login credentials or session rejected")

    async def async_login(self) -> bool:
        """Log in to the Smart Oil Gauge portal."""
        nonce = await self._async_fetch_login_nonce()

        payload = {
            "username": self.username,
            "user_pass": self.password,
            "ccf_nonce": nonce,
            "remember": "on",
        }

        _LOGGER.debug("Submitting login form to portal")
        try:
            async with self._session.post(
                LOGIN_URL,
                data=payload,
                headers=self._headers,
                allow_redirects=True,
                timeout=REQUEST_TIMEOUT,
            ) as r_login:
                self._check_http_status(
                    r_login.status, r_login.headers.get("Retry-After")
                )
                login_html = await r_login.text()
                self._validate_login_html(login_html, str(r_login.url))

                _LOGGER.info("Logged in successfully to Smart Oil Gauge")
                return True
        except TimeoutError as ex:
            _LOGGER.debug("Timeout error during login POST: %s", ex)
            raise CannotConnect("Timeout submitting credentials") from ex
        except aiohttp.ClientError as ex:
            _LOGGER.debug("Connection error during login POST: %s", ex)
            raise CannotConnect from ex

    def _process_json_payload(self, data: Any) -> dict[str, Any]:
        """Validate and return top-level JSON dictionary."""
        if not isinstance(data, dict):
            _LOGGER.debug("AJAX response is not a valid JSON object")
            raise CannotConnect("Unexpected response structure from server")
        return data

    async def async_get_tanks(self, retry_login: bool = True) -> list:
        """Fetch list of tanks and their metrics."""
        _LOGGER.debug("Requesting tanks list via AJAX")

        if not any(cookie.key == "PHPSESSID" for cookie in self._session.cookie_jar):
            _LOGGER.info("No session cookie found in cookie jar. Logging in first.")
            await self.async_login()

        ajax_payload = {"action": "get_tanks_list", "tank_id": "0"}
        headers = {
            **self._headers,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://app.smartoilgauge.com/app.php",
        }

        try:
            async with self._session.post(
                AJAX_URL, data=ajax_payload, headers=headers, timeout=REQUEST_TIMEOUT
            ) as r:
                if r.status in (401, 403) and retry_login:
                    _LOGGER.info("HTTP %s received. Retrying login...", r.status)
                    await self.async_login()
                    return await self.async_get_tanks(retry_login=False)

                self._check_http_status(r.status, r.headers.get("Retry-After"))

                try:
                    raw_data = await r.json()
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as ex:
                    _LOGGER.debug("AJAX response is not valid JSON: %s", ex)
                    raise CannotConnect("Invalid JSON response from server") from ex

                data = self._process_json_payload(raw_data)
                return await self._handle_tanks_response(data, retry_login)

        except TimeoutError as ex:
            _LOGGER.debug("Timeout error during AJAX fetch: %s", ex)
            raise CannotConnect("Timeout fetching tanks") from ex
        except aiohttp.ClientError as ex:
            _LOGGER.debug("Network error during AJAX fetch: %s", ex)
            raise CannotConnect from ex

    async def _handle_tanks_response(
        self, data: dict[str, Any], retry_login: bool
    ) -> list:
        """Process tanks response data and handle session expiry."""
        message = str(data.get("message") or "")
        status = data.get("Status")
        is_unauthorized = (
            data.get("result") == "error" and "Access Denied" in message
        ) or str(status) == "401"

        if is_unauthorized:
            if retry_login:
                _LOGGER.info("Session expired or unauthorized. Retrying login...")
                await self.async_login()
                return await self.async_get_tanks(retry_login=False)
            _LOGGER.debug("Session authorization failed repeatedly")
            raise InvalidAuth("Session authorization failed")

        if data.get("result") != "ok":
            error_msg = data.get("message", "Unknown error")
            _LOGGER.debug("AJAX returned error result: %s", error_msg)
            raise SmartOilGaugeException(f"Error from server: {error_msg}")

        tanks = data.get("tanks")
        if not isinstance(tanks, list):
            _LOGGER.debug("Tanks payload is not a list")
            raise SmartOilGaugeException("Invalid tank data received from server")

        valid_tanks: list[dict[str, Any]] = []
        discarded_count = 0
        for tank in tanks:
            if not isinstance(tank, dict):
                discarded_count += 1
                continue
            raw_id = tank.get("tank_id")
            if raw_id is None or not str(raw_id).strip():
                discarded_count += 1
                continue
            valid_tanks.append(tank)

        if discarded_count > 0:
            _LOGGER.warning("Discarded %d malformed tank records", discarded_count)

        if tanks and not valid_tanks:
            _LOGGER.debug("All returned tank records were malformed")
            raise SmartOilGaugeException("All returned tanks were malformed")

        _LOGGER.debug("Successfully fetched %d tanks", len(valid_tanks))
        return valid_tanks

    def _ajax_headers(self) -> dict[str, str]:
        return {
            **self._headers,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://app.smartoilgauge.com/app.php",
        }

    async def async_get_graph_data(
        self, tank_id: str, data_servers: str, retry_login: bool = True
    ) -> dict[str, Any]:
        """Fetch the hourly graph datasets (today, week, month, year) for a tank."""
        payload = {
            "action": "get_graph_data",
            "tank_id": tank_id,
            "data_servers": data_servers,
        }
        try:
            async with self._session.post(
                AJAX_URL,
                data=payload,
                headers=self._ajax_headers(),
                timeout=HISTORY_TIMEOUT,
            ) as r:
                if r.status in (401, 403) and retry_login:
                    await self.async_login()
                    return await self.async_get_graph_data(
                        tank_id, data_servers, retry_login=False
                    )
                self._check_http_status(r.status, r.headers.get("Retry-After"))
                try:
                    data = self._process_json_payload(await r.json(content_type=None))
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as ex:
                    raise CannotConnect("Invalid graph data response") from ex
        except TimeoutError as ex:
            raise CannotConnect("Timeout fetching graph data") from ex
        except aiohttp.ClientError as ex:
            raise CannotConnect from ex

        if data.get("result") != "ok":
            message = str(data.get("message") or "")
            if retry_login and "Access Denied" in message:
                await self.async_login()
                return await self.async_get_graph_data(
                    tank_id, data_servers, retry_login=False
                )
            raise SmartOilGaugeException(f"Graph data error: {message or data}")
        return data

    async def async_export_history(
        self,
        registration_id: str,
        start: date,
        end: date,
        retry_login: bool = True,
    ) -> str:
        """Download the hourly CSV export for a sensor registration.

        ``end`` is exclusive. The portal accepts ranges of up to two years.
        """
        form = {
            "registration_id": registration_id,
            "startdate": start.isoformat(),
            "enddate": end.isoformat(),
        }
        try:
            async with self._session.post(
                EXPORT_URL,
                params={"registration_id": registration_id},
                data=form,
                headers=self._headers,
                timeout=HISTORY_TIMEOUT,
            ) as r:
                if r.status in (401, 403) and retry_login:
                    await self.async_login()
                    return await self.async_export_history(
                        registration_id, start, end, retry_login=False
                    )
                self._check_http_status(r.status, r.headers.get("Retry-After"))
                text = await r.text()
        except TimeoutError as ex:
            raise CannotConnect("Timeout exporting history") from ex
        except aiohttp.ClientError as ex:
            raise CannotConnect from ex

        if not text.lstrip().lower().startswith("time,gallons"):
            if retry_login:
                _LOGGER.debug("Export did not return CSV; logging in again")
                await self.async_login()
                return await self.async_export_history(
                    registration_id, start, end, retry_login=False
                )
            raise SmartOilGaugeException("Export did not return CSV data")
        return text

    async def async_get_sensor_config(
        self, registration_id: str, retry_login: bool = True
    ) -> SensorConfig:
        """Read the portal's Sensor Config page for one sensor registration.

        This only loads the page; nothing is submitted.
        """
        try:
            async with self._session.get(
                SENSOR_CONFIG_URL,
                params={"registration_id": registration_id},
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            ) as r:
                if r.status in (401, 403) and retry_login:
                    await self.async_login()
                    return await self.async_get_sensor_config(
                        registration_id, retry_login=False
                    )
                self._check_http_status(r.status, r.headers.get("Retry-After"))
                html = await r.text()
        except TimeoutError as ex:
            raise CannotConnect("Timeout reading sensor configuration") from ex
        except aiohttp.ClientError as ex:
            raise CannotConnect from ex

        config = parse_sensor_config(html)
        if config is None:
            if retry_login:
                _LOGGER.debug("Sensor config page not returned; logging in again")
                await self.async_login()
                return await self.async_get_sensor_config(
                    registration_id, retry_login=False
                )
            raise SmartOilGaugeException("Sensor configuration form not found")
        return config

    async def async_set_upload_interval(
        self, registration_id: str, hours: int
    ) -> SensorConfig:
        """Change only the gauge's upload interval on the portal.

        The portal saves the whole sensor form at once, so the current form is
        read first and submitted unchanged except for the interval. The page
        is then read back to confirm that only the interval changed.
        """
        if not 1 <= hours <= 24:
            raise ValueError("Upload interval must be 1-24 hours")
        before = await self.async_get_sensor_config(registration_id)
        data = [
            (name, str(hours) if name == "upload_interval" else value)
            for name, value in before.fields
        ]
        if before.submit is not None:
            data.append(before.submit)
        try:
            async with self._session.post(
                SENSOR_CONFIG_URL,
                params={"registration_id": registration_id},
                data=data,
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            ) as r:
                self._check_http_status(r.status, r.headers.get("Retry-After"))
                await r.read()
        except TimeoutError as ex:
            raise CannotConnect("Timeout saving sensor configuration") from ex
        except aiohttp.ClientError as ex:
            raise CannotConnect from ex

        after = await self.async_get_sensor_config(registration_id)
        changed = before.compare(after, ignore={"upload_interval", NONCE_FIELD})
        if changed:
            raise SmartOilGaugeException(
                f"Sensor configuration fields changed unexpectedly: {changed}"
            )
        if after.upload_interval != hours:
            raise SmartOilGaugeException(
                f"Upload interval is {after.upload_interval} after saving {hours}"
            )
        _LOGGER.info(
            "Upload interval for sensor registration %s changed from %s to %s hours",
            registration_id,
            before.upload_interval,
            hours,
        )
        return after


@dataclass(slots=True)
class SensorConfig:
    """The Sensor Config form as the portal shows it."""

    fields: list[tuple[str, str]]
    submit: tuple[str, str] | None
    upload_interval: int | None
    num_tanks: int | None

    def values(self) -> dict[str, list[str]]:
        """Field values by name (radio groups and repeats keep all values)."""
        result: dict[str, list[str]] = {}
        for name, value in self.fields:
            result.setdefault(name, []).append(value)
        return result

    def compare(self, other: SensorConfig, ignore: set[str]) -> list[str]:
        """Names of fields whose values differ, apart from ``ignore``."""
        mine, theirs = self.values(), other.values()
        names = (set(mine) | set(theirs)) - ignore
        return sorted(n for n in names if mine.get(n) != theirs.get(n))


def parse_sensor_config(html: str) -> SensorConfig | None:
    """Parse the Sensor Config form like a browser would submit it."""
    soup = BeautifulSoup(html, "html.parser")
    select = soup.find("select", attrs={"name": "upload_interval"})
    if select is None:
        return None
    form = select.find_parent("form")
    if form is None:
        return None

    fields: list[tuple[str, str]] = []
    submit: tuple[str, str] | None = None
    for element in form.find_all(["input", "select", "textarea"]):
        name = element.get("name")
        if not name or element.has_attr("disabled"):
            continue
        kind = (element.get("type") or "").lower()
        if element.name == "input" and kind == "submit":
            submit = submit or (name, element.get("value", ""))
            continue
        value = _successful_value(element, kind)
        if value is not None:
            fields.append((name, value))

    values = dict(fields)
    return SensorConfig(
        fields=fields,
        submit=submit,
        upload_interval=_int_or_none(values.get("upload_interval")),
        num_tanks=_int_or_none(values.get("num_tanks")),
    )


def _successful_value(element: Any, kind: str) -> str | None:
    """The value a browser would submit for a form control, or None."""
    if element.name == "select":
        options = element.find_all("option")
        chosen = next((o for o in options if o.has_attr("selected")), None)
        chosen = chosen or (options[0] if options else None)
        if chosen is None:
            return None
        return chosen.get("value", chosen.get_text(strip=True))
    if element.name == "textarea":
        return element.get_text()
    if kind in ("button", "image", "reset", "file"):
        return None
    if kind in ("checkbox", "radio"):
        return element.get("value", "on") if element.has_attr("checked") else None
    return element.get("value", "")


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(str(value).strip())
    except TypeError, ValueError:
        return None
