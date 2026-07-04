Title: 🔒 fix: remove sensitive cookie and header logging

Description:
🎯 **What:** Removed logging statements in `client.py` that inadvertently exposed `PHPSESSID` cookies and full AJAX response headers in the Home Assistant logs.

⚠️ **Risk:** Writing session cookies or arbitrary backend headers to logs can lead to session hijacking or sensitive information disclosure if log files are accessible to untrusted users, services, or log aggregators.

🛡️ **Solution:** Removed the verbose `_LOGGER.info` calls for `cookies_in_jar`, `AJAX Request headers`, `AJAX Response status`, and `AJAX Response headers`. This ensures sensitive session tokens and headers are no longer persisted in the logs.
