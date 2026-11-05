# Tank entities

Entity IDs are examples; actual IDs depend on your Home Assistant configuration. Return to the [README](../README.md) for setup.

## Entities

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
