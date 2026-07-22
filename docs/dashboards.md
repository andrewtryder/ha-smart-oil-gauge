# Dashboard Widgets & Daily Usage Tracking

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
  - entity: sensor.house_tank_last_checked
    name: Last Checked
```

### Tracking Total Fuel Consumed Historically
Since the tank level sensor (`sensor.oil_tank_level`) *decreases* when oil is burned, you can construct a Home Assistant Template Sensor that calculates cumulative drops, and reset it using the built-in **Utility Meter** helper:

#### 1. Add a Template Sensor in `configuration.yaml`
```yaml
template:
  - trigger:
      - platform: state
        entity_id: sensor.house_tank_oil_level
    sensor:
      - name: "Total Oil Consumed"
        unique_id: total_oil_consumed
        unit_of_measurement: "gal"
        device_class: volume
        state_class: total_increasing
        state: >
          {% if trigger.from_state is not none and trigger.to_state is not none %}
            {% set from_val = trigger.from_state.state | float(none) %}
            {% set to_val = trigger.to_state.state | float(none) %}
            {% set current = this.state | float(0) %}
            {% if from_val is not none and to_val is not none and from_val > to_val %}
              {{ (current + (from_val - to_val)) | round(2) }}
            {% else %}
              {{ current }}
            {% endif %}
          {% else %}
            {{ this.state | float(0) }}
          {% endif %}
```
#### 2. Create a Utility Meter Helper
Go to **Settings** -> **Devices & Services** -> **Helpers** -> **Create Helper** -> **Utility Meter**. Set the input sensor to your newly created template sensor, and set the reset cycle to **Daily**, **Weekly**, or **Monthly**. Home Assistant will automatically log and graph your consumption history.
