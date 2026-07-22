# Smart Oil Gauge integration for Home Assistant

<p align="center">
  <img src="https://play-lh.googleusercontent.com/sgao5kv33PhINKgy78fkO0xjpRd-X8U3VoK0KhJkVKUhHGXwu7ss_vVvd-DZAbZZBSmR1l69892sjp5xHxyb=w600-h300-pc0xffffff-pd" alt="Smart Oil Gauge Logo" width="400">
</p>

[![validate](https://img.shields.io/github/actions/workflow/status/andrewtryder/ha-smart-oil-gauge/validate.yml?branch=main&style=for-the-badge)](https://github.com/andrewtryder/ha-smart-oil-gauge/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz/)
[![release](https://img.shields.io/github/v/release/andrewtryder/ha-smart-oil-gauge?style=for-the-badge)](https://github.com/andrewtryder/ha-smart-oil-gauge/releases)
[![license](https://img.shields.io/github/license/andrewtryder/ha-smart-oil-gauge?style=for-the-badge)](https://github.com/andrewtryder/ha-smart-oil-gauge/blob/main/LICENSE)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=andrewtryder&repository=ha-smart-oil-gauge&category=integration)


A HACS-compatible Home Assistant custom integration for the **Smart Oil Gauge** by Connected Consumer Fuel. This integration logs into the Smart Oil Gauge web portal, retrieves tank metrics via AJAX, and registers each tank as a device with associated sensors.

<p align="center">
  <img src="images/device_card.png" alt="Smart Oil Gauge Device Card" width="600">
</p>

## Features

### Entities

| Entity Name | Entity ID | Description |
| :--- | :--- | :--- |
| **Oil Level** | `sensor.oil_tank_level` | Remaining fuel level in gallons (physical sensor reading or model estimate). |
| **Oil Percentage** | `sensor.oil_tank_percentage` | Percentage of total tank capacity remaining. |
| **Daily Usage Rate** | `sensor.oil_tank_daily_usage_rate` | Rolling average daily fuel consumption (`gal/day`). |
| **Estimated Runout Date** | `sensor.oil_tank_estimated_runout_date` | Estimated date when fuel reaches 0 gallons based on current usage. |
| **Last Refill Amount** | `sensor.oil_tank_last_refill_amount` | Gallons added during the most recent detected refill. |
| **Last Refill Date** | `sensor.oil_tank_last_refill_date` | Date and time when the last refill occurred. |
| **Max Level** | `sensor.oil_tank_max_level` | Total nominal tank capacity in gallons. |
| **Max Fill** | `sensor.oil_tank_max_fill` | Remaining fillable tank capacity in gallons. |
| **Days to 1/4** | `sensor.oil_tank_days_to_1_4` | Estimated days remaining until fuel reaches 25% capacity. |
| **Days to 1/8** | `sensor.oil_tank_days_to_1_8` | Estimated days remaining until fuel reaches 12.5% capacity. |
| **Battery** | `sensor.oil_tank_battery` | Battery health status (`Excellent`, `Good`, `Fair`, `Poor`). |
| **Last Portal Update** | `sensor.oil_tank_last_portal_update` | Timestamp of the last successful data refresh from the portal. |
| **Low Fuel Alert** | `binary_sensor.oil_tank_low_fuel_alert` | Alert triggered when fuel level drops below the low threshold. |

### Key Capabilities
- **Multi-Tank Support**: Automatically discovers all oil tanks linked to your account.
- **Account Reauthentication**: Prompts you to update credentials if your password changes or session expires.
- **System Repairs**: Notifies you in Home Assistant if the vendor portal changes in a way that breaks data collection.
- **Diagnostics & Portal Access**: Download sanitized diagnostic reports and open the Smart Oil Gauge portal directly from the device page.

## Documentation

- [Advanced Usage: Energy & Consumption Tracking](docs/advanced-usage.md)
- [Dashboard Widgets & Daily Usage Tracking](docs/dashboards.md)

## Installation

### Method 1: HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. In the HACS interface, click on **Integrations** (three dots in the top-right corner) and select **Custom repositories**.
3. Enter the URL of this repository: `https://github.com/andrewtryder/ha-smart-oil-gauge` (or your personal fork).
4. Select **Integration** as the category, and click **Add**.
5. Find **Smart Oil Gauge** in the integration list and click **Download**.
6. Restart Home Assistant to apply changes.

### Method 2: Manual Installation

1. Download the latest release source code.
2. Copy the `custom_components/smart_oil_gauge/` directory into your Home Assistant's `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration

1. In the Home Assistant UI, go to **Settings** -> **Devices & Services** -> **Integrations**.
2. Click **+ Add Integration** in the bottom right.
3. Search for **Smart Oil Gauge** and select it.
4. Enter your Smart Oil Gauge username (email) and password, then click **Submit**.

---

## Polling Interval & Options

The polling interval is configurable from **1 to 24 hours**, with **6 hours** as the recommended default. You can adjust the polling frequency at any time via the integration's **Configure** / Options flow in Home Assistant.

> [!NOTE]
> The physical gauge hardware typically wakes up and updates the servers 1-3 times a day. Polling the cloud portal more frequently does not provide fresher data, and risks triggering rate limits or account blocks.

## License

This project is licensed under the MIT License.
