# Advanced Usage: Energy & Consumption Tracking

The Smart Oil Gauge API provides the current oil level and a rolling average usage rate. To track daily, monthly, and yearly consumption or convert fuel volume into energy usage (kWh), you can configure a Home Assistant configuration package.

Here is your updated configuration package configured to work with the sensors exposed by this integration. To use it, create or update a YAML file in your Home Assistant configuration directory (e.g., `/config/packages/oil_totals.yaml`):

```yaml
# /config/packages/oil_totals.yaml

input_number:
  oil_kwh_per_gal:
    name: Oil energy content (kWh/gal)
    unit_of_measurement: "kWh/gal"
    min: 0
    max: 100
    step: 0.1
    mode: box
    initial: 40.6

  oil_system_efficiency:
    name: Oil system efficiency (0-1)
    min: 0
    max: 1
    step: 0.01
    mode: box
    initial: 0.85

sensor:
  # 1) Rate-of-change of remaining tank gallons (negative on burn, positive on refill)
  # NOTE: Replace "sensor.house_tank_oil_level" with your actual tank level sensor ID
  - platform: derivative
    name: Oil Tank Change Rate GPH
    unique_id: oil_tank_change_rate_gph
    source: sensor.house_tank_oil_level
    unit_time: h
    round: 4

  # 2) Integrate consumption rate (gal/h) into total gallons used (gal)
  - platform: integration
    name: Oil Total Used Gal Raw
    unique_id: oil_total_used_gal_raw
    source: sensor.oil_consumption_rate_gph
    unit_time: h
    method: trapezoidal
    round: 3

utility_meter:
  oil_energy_daily:
    source: sensor.oil_total_used_kwh
    name: Oil Energy Daily
    unique_id: oil_energy_daily
    cycle: daily
    periodically_resetting: false
    always_available: true

  oil_energy_monthly:
    source: sensor.oil_total_used_kwh
    name: Oil Energy Monthly
    unique_id: oil_energy_monthly
    cycle: monthly
    periodically_resetting: false
    always_available: true

  oil_energy_yearly:
    source: sensor.oil_total_used_kwh
    name: Oil Energy Yearly
    unique_id: oil_energy_yearly
    cycle: yearly
    periodically_resetting: false
    always_available: true

template:
  - sensor:
      - name: Oil Consumption Rate GPH
        unique_id: oil_consumption_rate_gph
        unit_of_measurement: "gal/h"
        device_class: volume_flow_rate
        state_class: measurement
        state: >
          {% set r = states('sensor.oil_tank_change_rate_gph') %}
          {% if not is_number(r) %}
            {% set r = states('sensor.oil_tank_change_rate') %}
          {% endif %}

          {% if not is_number(r) %}
            {{ none }}
          {% else %}
            {% set rate = r | float %}
            {% if rate < -0.02 %}
              {{ (-rate) | round(3) }}
            {% else %}
              0
            {% endif %}
          {% endif %}
        availability: >
          {{ is_number(states('sensor.oil_tank_change_rate_gph'))
             or is_number(states('sensor.oil_tank_change_rate')) }}

      # 4) Total gallons used (monotonic) with proper metadata for long-term stats
      - name: Oil Total Used (gal)
        unique_id: oil_total_used_gal
        default_entity_id: sensor.oil_total_used_gal
        unit_of_measurement: "gal"
        device_class: volume
        state_class: total_increasing
        state: >
          {{ states('sensor.oil_total_used_gal_raw') | float(0) | round(2) }}
        availability: "{{ is_number(states('sensor.oil_total_used_gal_raw')) }}"

      # 5) Convert gallons used → kWh energy consumption
      - name: Oil Total Used (kWh)
        unique_id: oil_total_used_kwh
        default_entity_id: sensor.oil_total_used_kwh
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        state: >
          {% set gal = states('sensor.oil_total_used_gal') | float(0) %}
          {% set kwhpg = states('input_number.oil_kwh_per_gal') | float(40.6) %}
          {% set eff = states('input_number.oil_system_efficiency') | float(0.85) %}
          {{ (gal * kwhpg * eff) | round(2) }}
        availability: "{{ is_number(states('sensor.oil_total_used_gal')) }}"

  - sensor:
      # Convenience "last period" helpers
      - name: Oil Energy Yesterday
        unique_id: oil_energy_yesterday
        unit_of_measurement: "kWh"
        state: "{{ state_attr('sensor.oil_energy_daily', 'last_period') | float(0) }}"

      - name: Oil Energy Last Month
        unique_id: oil_energy_last_month
        unit_of_measurement: "kWh"
        state: "{{ state_attr('sensor.oil_energy_monthly', 'last_period') | float(0) }}"

      - name: Oil Energy Last Year
        unique_id: oil_energy_last_year
        unit_of_measurement: "kWh"
        state: "{{ state_attr('sensor.oil_energy_yearly', 'last_period') | float(0) }}"
```
