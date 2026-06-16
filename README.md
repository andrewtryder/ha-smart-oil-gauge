# Smart Oil Gauge integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![validate](https://github.com/andrewtryder/ha-smart-oil-gauge/actions/workflows/validate.yml/badge.svg?style=for-the-badge)](https://github.com/andrewtryder/ha-smart-oil-gauge/actions/workflows/validate.yml)
[![release](https://img.shields.io/github/v/release/andrewtryder/ha-smart-oil-gauge?style=for-the-badge)](https://github.com/andrewtryder/ha-smart-oil-gauge/releases)
[![license](https://img.shields.io/github/license/andrewtryder/ha-smart-oil-gauge?style=for-the-badge)](https://github.com/andrewtryder/ha-smart-oil-gauge/blob/main/LICENSE)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&style=for-the-badge)](https://github.com/pre-commit/pre-commit)
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=andrewtryder&repository=ha-smart-oil-gauge&category=integration)


A HACS-compatible Home Assistant custom integration for the **Smart Oil Gauge** by Connected Consumer Fuel. This integration logs into the Smart Oil Gauge web portal, retrieves the current tank data via AJAX, and registers the tank as a device with associated sensors.

## Features

- **Oil Level Sensor** (`sensor.oil_tank_level`): Remaining fuel level in gallons (preferring physical sensor readings and falling back to model estimates).
- **Oil Percentage Sensor** (`sensor.oil_tank_percentage`): Percentage of the tank capacity that is full.
- **Daily Usage Rate Sensor** (`sensor.oil_tank_daily_usage_rate`): Average rolling daily consumption rate in gallons per day (`gal/day`).
- **Battery Sensor** (`sensor.oil_tank_battery`): Battery health diagnostic status (e.g., `Excellent`, `Good`, `Fair`, `Poor`), with dynamic battery icons.
- **Automatic Device Registry**: Groups all sensors for a single physical tank together as one device. Supports multiple tanks under a single account.

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

## Local Development and Testing

We welcome community contributions. Below are the guidelines for testing, running linters, and verifying your changes.

### 1. Local Python Environment Setup
We use Python virtual environments to manage linter configurations and test suites locally:
```bash
# Initialize virtual environment
python3 -m venv .venv

# Install test and development dependencies
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest pytest-homeassistant-custom-component pytest-cov pytest-asyncio aresponses ruff pre-commit
```

### 2. Pre-commit & Ruff Checks
We enforce style checks and import sorting using `ruff`. Run them before submitting code:
```bash
# Install git hooks
.venv/bin/pre-commit install

# Run checks manually on all files
.venv/bin/pre-commit run --all-files
```

### 3. Running Unit Tests
We use `pytest` combined with `pytest-homeassistant-custom-component` to run our test suite:
```bash
.venv/bin/pytest
```
To run tests with code coverage outputs:
```bash
.venv/bin/pytest --cov=custom_components/smart_oil_gauge --cov-report=term-missing
```

### 4. Integration Core Verification (`hassfest`)
We validate the custom component's structural sanity against Home Assistant core requirements using `hassfest` via Docker:
```bash
docker run --rm -v "$(pwd):/github/workspace" ghcr.io/home-assistant/hassfest
```

### 5. Running Home Assistant Locally (Sandbox Testing)
You can test the custom component in a real Home Assistant container on your Mac:
```bash
docker run -d \
  --name homeassistant-test \
  --privileged \
  -v "$(pwd)/custom_components:/config/custom_components" \
  -p 8123:8123 \
  ghcr.io/home-assistant/home-assistant:stable
```
Once launched, open `http://localhost:8123` in your browser, perform the onboarding steps, and add the **Smart Oil Gauge** integration.

---

## Dashboard Widgets & Daily Usage Tracking

### Lovelace Dashboard Card Examples

#### Gauge Card (Visual fill)
```yaml
type: gauge
entity: sensor.house_tank_oil_percentage
name: Oil Tank Level
unit: '%'
severity:
  green: 30
  yellow: 15
  red: 0
```

#### Entities Card (Complete overview)
```yaml
type: entities
title: Heating Oil Tank
entities:
  - entity: sensor.house_tank_oil_level
    name: Gallons Remaining
  - entity: sensor.house_tank_oil_percentage
    name: Tank Fill
  - entity: sensor.house_tank_daily_usage_rate
    name: Consumption Rate
  - entity: sensor.house_tank_battery
    name: Gauge Battery
```

### Tracking Total Fuel Consumed Historically
Since the tank level sensor (`sensor.oil_tank_level`) *decreases* when oil is burned, you can construct a Home Assistant Template Sensor that calculates cumulative drops, and reset it using the built-in **Utility Meter** helper:

#### 1. Add a Template Sensor in `configuration.yaml`
```yaml
template:
  - sensor:
      - name: "Total Oil Consumed"
        unique_id: total_oil_consumed
        unit_of_measurement: "gal"
        device_class: water
        state_class: total_increasing
        state: >
          # Custom logic to accumulate level drops, ignoring fills.
```
#### 2. Create a Utility Meter Helper
Go to **Settings** -> **Devices & Services** -> **Helpers** -> **Create Helper** -> **Utility Meter**. Set the input sensor to your newly created template sensor, and set the reset cycle to **Daily**, **Weekly**, or **Monthly**. Home Assistant will automatically log and graph your consumption history.

---

## Smart Polling Rate

This integration is configured to poll the Smart Oil Gauge portal exactly **once every 6 hours (21,600 seconds)**.

> [!NOTE]
> The physical gauge hardware only wakes up and updates the servers 1-3 times a day. Polling the cloud portal more frequently does not provide fresher data, and risks triggering anti-scraping blocks or locking your account.

## License

This project is licensed under the MIT License.
