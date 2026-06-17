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
