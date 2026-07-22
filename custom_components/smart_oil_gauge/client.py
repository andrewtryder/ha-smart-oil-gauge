"""Client module for the Smart Oil Gauge integration."""

import json
import logging
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from .const import USER_AGENT

_LOGGER = logging.getLogger(__name__)

LOGIN_URL = "https://app.smartoilgauge.com/login.php"
AJAX_URL = "https://app.smartoilgauge.com/ajax/main_ajax.php"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


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
