# Tank entities

Entity IDs are examples; actual IDs depend on your Home Assistant configuration. Return to the [README](../README.md) for setup.

## Entities

| Entity Name | Entity ID | Description |
| :--- | :--- | :--- |
| **Oil Level** | `sensor.oil_tank_level` | Remaining fuel level in gallons (physical sensor reading or model estimate). |
| **Oil Percentage** | `sensor.oil_tank_percentage` | Percentage of total tank capacity remaining. |
| **Daily Usage Rate** | `sensor.oil_tank_daily_usage_rate` | Rolling average daily fuel consumption (`gal/day`). |
| **Estimated Runout Date** | `sensor.oil_tank_estimated_runout_date` | Estimated date when fuel reaches 0 gallons based on current usage. |
| **Last Refill Amount** | `sensor.oil_tank_last_refill_amount` | Gallons added during the most recent detected refill. Attribute `equalizing` ("Refill equalization in progress") is `true` while the level is still rising after a delivery. A delivery itself takes minutes; a level that keeps climbing for hours afterwards is a second tank equalizing through its connecting line, or the oil settling. The amount keeps updating until the level levels off. |
| **Last Refill Date** | `sensor.oil_tank_last_refill_date` | Date and time when the last refill occurred. |
| **Max Level** | `sensor.oil_tank_max_level` | Total nominal tank capacity in gallons. |
| **Max Fill** | `sensor.oil_tank_max_fill` | Remaining fillable tank capacity in gallons. |
| **Days to 1/4** | `sensor.oil_tank_days_to_1_4` | Estimated days remaining until fuel reaches 25% capacity. |
| **Days to 1/8** | `sensor.oil_tank_days_to_1_8` | Estimated days remaining until fuel reaches 12.5% capacity. |
| **Battery** | `sensor.oil_tank_battery` | Battery health status (`Excellent`, `Good`, `Fair`, `Poor`). |
| **Last Portal Sync** | `sensor.oil_tank_last_portal_sync` | When Home Assistant last synced with the portal successfully. (Renamed from "Last Portal Update"; existing installs keep their `..._last_portal_update` entity ID.) |
| **Next Portal Sync** | `sensor.oil_tank_next_portal_sync` | When Home Assistant will next check the portal: the next fixed-interval poll, or (with the experimental gauge-schedule option) shortly after the next expected upload or the next retry if an upload is late. |
| **Last Gauge Upload** | `sensor.oil_tank_last_gauge_upload` | When the gauge last uploaded its readings to the portal. |
| **Next Gauge Upload** | `sensor.oil_tank_next_gauge_upload` | The earliest time the gauge could next upload. An expected upload stays shown for the 5 minutes until the sync that checks for it, then moves on. While an interval change is pending, both the old and new interval are possible (`possible_uploads`). Shows unknown when every expected time has passed (`overdue: true`). Also `next_sync` and `interval_in_use_hours`. |
| **Upload Interval In Use** | `sensor.oil_tank_upload_interval_in_use` | The upload interval (hours) the gauge is using now, which sets when the next upload is expected. Differs from the Upload interval select while a change is pending. Attributes: `portal_interval_hours`, `pending`, `source` (`observed` once confirmed by upload gaps, otherwise `portal`). |
| **Upload Interval Change Pending** | `binary_sensor.oil_tank_upload_interval_change_pending` | On while the portal's upload interval differs from the one the gauge is using. The gauge fetches settings far less often than it uploads, so a change can take a day or more; it clears when an upload gap matches the new setting. Attributes: `portal_interval_hours`, `gauge_interval_hours`, `pending_since`. |
| **Sync Now** (button) | `button.oil_tank_sync_now` | Checks the portal for new readings immediately. |
| **Upload Interval** (select) | `select.oil_tank_upload_interval` | Only present when the experimental *Allow changing the gauge's upload interval* option is on. The gauge's upload interval (hours) as set on the portal. Changing it updates the portal; the gauge picks it up the next time it fetches its settings, which can take a day or more. Attributes: `effective_interval_hours` (in use now), `pending`, `interval_source` (`observed` or `portal`), `number_of_tanks`. |
| **Import History** (button) | `button.oil_tank_import_history` | Only present when the experimental *Import full portal history* option is on. Downloads the gauge's full hourly history from the portal and adds it to Home Assistant's statistics (and history, if backfill is on). Safe to press again; a press while an import is running is ignored. |
| **Low Fuel Alert** | `binary_sensor.oil_tank_low_fuel_alert` | Alert triggered when fuel level drops below the low threshold. |
