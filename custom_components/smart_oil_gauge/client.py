"""Client module for the Smart Oil Gauge integration."""

import logging

import aiohttp
from bs4 import BeautifulSoup

from .const import USER_AGENT

_LOGGER = logging.getLogger(__name__)

LOGIN_URL = "https://app.smartoilgauge.com/login.php"
AJAX_URL = "https://app.smartoilgauge.com/ajax/main_ajax.php"


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

    async def async_login(self) -> bool:
        """Log in to the Smart Oil Gauge portal."""
        _LOGGER.debug("Fetching login page to extract nonce")
        try:
            async with self._session.get(LOGIN_URL, headers=self._headers) as r:
                if r.status != 200:
                    _LOGGER.error("Failed to fetch login page: %s", r.status)
                    raise CannotConnect("Failed to connect to login page")
                html = await r.text()
        except aiohttp.ClientError as ex:
            _LOGGER.error("Connection error during login fetch: %s", ex)
            raise CannotConnect from ex

        # Parse nonce
        soup = BeautifulSoup(html, "html.parser")
        nonce_input = soup.find("input", {"name": "ccf_nonce"})
        if not nonce_input:
            _LOGGER.error("Could not find ccf_nonce on login page")
            raise CannotConnect("CSRF token ccf_nonce not found in page HTML")

        nonce = nonce_input.get("value")
        _LOGGER.debug("Found ccf_nonce: %s", nonce)

        payload = {
            "username": self.username,
            "user_pass": self.password,
            "ccf_nonce": nonce,
            "remember": "on",
        }

        _LOGGER.debug("Submitting login form to portal")
        try:
            async with self._session.post(
                LOGIN_URL, data=payload, headers=self._headers, allow_redirects=True
            ) as r_login:
                if r_login.status != 200:
                    _LOGGER.error("Login submission returned status %s", r_login.status)
                    raise CannotConnect("Failed to submit login credentials")

                login_html = await r_login.text()
                # Check for errors in the returned html page
                if "app_error" in login_html:
                    soup_err = BeautifulSoup(login_html, "html.parser")
                    err_msg = soup_err.find(class_="app_error")
                    if err_msg and err_msg.get_text(strip=True):
                        error_text = err_msg.get_text(strip=True)
                        _LOGGER.warning(
                            "Authentication failed with message: %s", error_text
                        )
                        raise InvalidAuth(error_text)

                # Check if we were successfully redirected/logged in
                final_url = str(r_login.url)
                if "app.php" not in final_url:
                    _LOGGER.warning("Login redirect URL was not app.php: %s", final_url)
                    raise InvalidAuth("Invalid login credentials or session rejected")

                _LOGGER.info("Logged in successfully to Smart Oil Gauge")
                return True
        except aiohttp.ClientError as ex:
            _LOGGER.error("Connection error during login POST: %s", ex)
            raise CannotConnect from ex

    async def async_get_tanks(self, retry_login: bool = True) -> list:
        """Fetch list of tanks and their metrics."""
        _LOGGER.debug("Requesting tanks list via AJAX")

        # If no session cookies are present, log in first
        if not any(cookie.key == "PHPSESSID" for cookie in self._session.cookie_jar):
            _LOGGER.info("No session cookie found in cookie jar. Logging in first.")
            await self.async_login()

        ajax_payload = {
            "action": "get_tanks_list",
            "tank_id": "0",
        }

        # Add AJAX headers
        headers = {
            **self._headers,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://app.smartoilgauge.com/app.php",
        }

        # Debug cookies in jar
        cookies_in_jar = {
            cookie.key: cookie.value for cookie in self._session.cookie_jar
        }
        _LOGGER.info("Cookies before AJAX post: %s", cookies_in_jar)
        _LOGGER.info("AJAX Request headers: %s", headers)

        try:
            async with self._session.post(
                AJAX_URL, data=ajax_payload, headers=headers
            ) as r:
                _LOGGER.info("AJAX Response status: %s", r.status)
                _LOGGER.info("AJAX Response headers: %s", dict(r.headers))
                if r.status != 200:
                    _LOGGER.error("AJAX call failed with status: %s", r.status)
                    raise CannotConnect("AJAX request failed")

                try:
                    data = await r.json()
                except Exception as ex:
                    # Let's inspect the returned text to see if it is not JSON
                    text = await r.text()
                    _LOGGER.error("AJAX response is not JSON: %s", text[:500])
                    raise CannotConnect("Invalid JSON response from server") from ex

                # Handle Access Denied or 401 (session expired/unauthorized)
                is_unauthorized = (
                    data.get("result") == "error"
                    and "Access Denied" in data.get("message", "")
                ) or data.get("Status") == 401
                if is_unauthorized:
                    if retry_login:
                        _LOGGER.info(
                            "Session expired or unauthorized. Retrying login..."
                        )
                        await self.async_login()
                        return await self.async_get_tanks(retry_login=False)
                    else:
                        _LOGGER.error("Session authorization failed repeatedly")
                        raise InvalidAuth("Session authorization failed")

                if data.get("result") != "ok":
                    error_msg = data.get("message", "Unknown error")
                    _LOGGER.error(
                        "AJAX returned error result: %s. Full response: %s",
                        error_msg,
                        data,
                    )
                    raise SmartOilGaugeException(f"Error from server: {error_msg}")

                tanks = data.get("tanks", [])
                _LOGGER.debug("Successfully fetched %d tanks", len(tanks))
                return tanks

        except aiohttp.ClientError as ex:
            _LOGGER.error("Network error during AJAX fetch: %s", ex)
            raise CannotConnect from ex
