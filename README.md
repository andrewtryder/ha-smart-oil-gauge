# Smart Oil Gauge for Home Assistant

<img src="custom_components/smart_oil_gauge/brand/logo.png" alt="Smart Oil Gauge integration logo" width="180">

See how much heating oil remains, track your tanks, and estimate when you may need a refill in Home Assistant.

[![Latest release](https://img.shields.io/github/v/release/andrewtryder/ha-smart-oil-gauge?style=flat-square)](https://github.com/andrewtryder/ha-smart-oil-gauge/releases/latest)
[![Validation on main](https://img.shields.io/github/actions/workflow/status/andrewtryder/ha-smart-oil-gauge/validate.yml?branch=main&style=flat-square&label=validation)](https://github.com/andrewtryder/ha-smart-oil-gauge/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/andrewtryder/ha-smart-oil-gauge?style=flat-square)](LICENSE)
[![HACS custom integration](https://img.shields.io/badge/HACS-Custom-orange?style=flat-square)](https://my.home-assistant.io/redirect/hacs_repository/?owner=andrewtryder&repository=ha-smart-oil-gauge&category=integration)

![Smart Oil Gauge device card in Home Assistant](images/device_card.png)

## What can I do with it?

- See remaining gallons and tank percentage for each linked tank.
- Track estimated daily use, runout date, recent refills, and battery status.
- Optionally (experimental, off by default) see every hourly reading in Home Assistant's history at the time it was taken, even though the gauge uploads them in batches (see [Hourly history](#hourly-history)).
- Build low-fuel alerts and dashboards using Home Assistant entities.
- Get reauthentication prompts and repair notices when portal access needs attention.

Runout dates and usage are estimates based on available data; check your tank and supplier information before relying on them.

## Requirements and compatibility

You need Home Assistant with HACS (or the built-in Home Assistant Marketplace in **2026.11+**), a [Smart Oil Gauge portal account](https://app.smartoilgauge.com), and at least one tank already linked to that account. This integration reads the vendor portal over the internet; it supports multiple tanks on the same account.

## Install with HACS or Home Assistant Marketplace

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=andrewtryder&repository=ha-smart-oil-gauge&category=integration)

1. Click the **Open your Home Assistant instance** button above (backwards compatible: opens **HACS** on earlier versions and the built-in **Home Assistant Marketplace** on **2026.11+**), or manually add `https://github.com/andrewtryder/ha-smart-oil-gauge` as a custom repository in the **Integration** category.
2. Find and install **Smart Oil Gauge**.
3. Restart Home Assistant.

For manual installation, download the latest release and copy `custom_components/smart_oil_gauge/` into your Home Assistant configuration's `custom_components` directory, then restart.

## First-time setup

1. Go to **Settings → Devices & services → Add integration** and select **Smart Oil Gauge**.
2. Enter your portal email and password and choose a polling interval from 1 to 24 hours. (An experimental option can instead sync on the gauge's own upload schedule; see [Sync timing](#sync-timing).)
3. Submit the form. Each discovered tank appears as a device with its available sensors.

You can change the interval later in the integration's **Configure** options.

## Hourly history

The gauge takes a reading every hour but, to save battery, uploads them in batches (every 1–24 hours, set in the gauge's own configuration). Without help, Home Assistant only sees the newest reading at each upload, stamped with the time Home Assistant polled.

This integration fills in the gaps. **Last gauge upload** and refill detection are always on. The history backfill and the history import are **experimental and opt-in**: both are off by default and must be turned on under **Configure**. With them off, the integration never writes past readings to the recorder, and upgrading changes nothing in your existing history.

- **Last gauge upload** shows when the gauge actually uploaded, not when Home Assistant synced.
- **On every new upload** (when *Backfill sensor history* is on) the hourly readings for the past week are fetched and written into Home Assistant's history **at the time each reading was taken**. The built-in history graph, the entity's more-info dialog, and the History panel all show the full hourly curve. Rows recorded between uploads that held a stale value are corrected to the true reading.
- **Long-term statistics** for the same hours are updated (also only with backfill on), so history older than the recorder's keep window (10 days by default) is also accurate.
- **History import** (when *Import full portal history* is on) downloads the gauge's full hourly history from the portal's export once and adds it to long-term statistics, plus state history within the keep window if backfill is also on. An **Import history** button appears on the tank's device page to run it again; it is safe to repeat, and a second press while an import is running is ignored.
- **Refills** are detected from the hourly readings and reported as one refill starting at its real time. A delivery takes minutes, but the gauged level can keep rising for hours afterwards, for example while a second tank equalizes through its connecting line. During that time **Last refill amount** keeps updating and its `equalizing` attribute ("Refill equalization in progress") is `true`; it turns `false` once the level settles.

Both experimental options are under **Configure** and are off unless you turn them on.

> **Experimental:** Home Assistant has no official API for writing past states, so the history backfill writes to the recorder database directly, using the recorder's own database models inside its own thread. It is written to work with SQLite, MariaDB/MySQL, and PostgreSQL, but it relies on Home Assistant internals that can change in any release. If the recorder is migrating or its database layout is not what this version expects, the backfill is skipped with a warning and statistics are still updated. As with any database change, keep regular backups.

## Sync timing

By default the integration polls the portal every N hours, as set during setup. Polling doesn't use the gauge's battery, but the gauge only uploads on its own interval (1–24 hours, set on the portal under **Sensor Config**), so a fixed poll can catch an upload up to N hours late.

**Follow the gauge's upload schedule** (experimental, off by default, under **Configure**) reads the gauge's upload interval from the portal and syncs **a few minutes after each expected upload** instead:

- **Next sync** = the gauge's last upload + its upload interval + 5 minutes.
- **Late upload** (weak signal, low battery): tries again 15, 45 and 105 minutes after it was due. If another upload is still possible later (for example while an interval change is pending), it then waits for that; otherwise it keeps trying hourly.
- **No syncs in between:** battery and level only change when the gauge uploads. With a 12-hour interval that's two syncs a day, plus retries only when an upload is late. (A 25-hour limit is kept as a safety net.)
- **One schedule for all tanks:** a single request updates every tank, so it syncs when the earliest one is due.

### How the gauge picks up a new upload interval

The gauge **uploads** on its interval, but it **fetches its settings** from the portal far less often, roughly once a day and sometimes less. The portal itself notes that a change "can take up to a few days to take effect." Watching a real gauge:

- **12 h → 1 h:** the gauge made two more 12-hour uploads (about 20 hours) before switching to hourly.
- **1 h → 2 h:** the gauge kept uploading every hour through the evening; the change hadn't been picked up hours later.
- **→ 12 h:** set in the morning, picked up within a day.

So a change does not take effect at the next upload, and its timing can't be predicted. The integration doesn't guess:

- **The interval in use is learned from the gauge's uploads.** A change on the portal is shown as *pending* (with the time it was made) until an upload gap matches the new setting. A double-length gap is treated as a missed upload, not a new interval; two consistent gaps that match neither setting are trusted.
- **While a change is pending, both the old and the new interval are possible** for each upload, and the sync follows whichever slot comes first.
- **Next gauge upload shows the earliest upload still possible.** An expected upload stays shown for the 5 minutes until the sync that checks for it (so it may read "2 minutes ago" while due); after that it moves to the next possible upload, or shows *unknown* with `overdue: true` if none is left.

### Entities

Each tank gets:

- **Sync now** button: checks the portal immediately (in either mode).
- **Upload interval in use** sensor: the interval the gauge is actually using, with the portal's setting and whether a change is pending.
- **Upload interval change pending**: on while the portal setting differs from what the gauge is doing, with the time of the change.
- **Next gauge upload** and **Next portal sync** sensors.
- **Upload interval** control, only with **Allow changing the gauge's upload interval** (experimental, off by default) turned on: changes the gauge's upload interval on the portal. The portal saves its whole Sensor Config form at once, so the integration resubmits it with every other field unchanged and reads it back to confirm only the interval changed. The gauge applies it when it next fetches its settings (see above).

## What you'll see in Home Assistant

Depending on the data available, each tank can show level, percentage, daily usage, estimated runout date, refill information, capacity, battery health, and a low-fuel alert. See the [entity reference](docs/entities.md) for examples, and [dashboard examples](docs/dashboards.md) for ideas.

## Common problems and troubleshooting

- **No tank or stale reading:** check that the tank is linked and updated in the vendor portal. The physical gauge uploads only at its configured interval; polling more often than hourly does not make readings fresher. Missed hours are filled in automatically at the next upload.
- **Authentication failed:** update the credentials when Home Assistant prompts for reauthentication.
- **Portal data cannot be read:** check Home Assistant repairs and diagnostics. Review diagnostics before sharing them and never post credentials.

## Limitations, safety, and privacy

The integration depends on the vendor's web portal and its available data. Oil level may be a physical reading or an estimate. Runout and daily-use values are estimates, not a guarantee of remaining fuel. A portal change or outage can interrupt updates.

Removing the integration through **Settings → Devices & services** also removes its locally stored refill and backfill state and related repair notifications; history already written to the recorder stays until the recorder purges it. It does not change the vendor portal account.

## More documentation

- [Tank entities](docs/entities.md)
- [Energy and consumption tracking](docs/advanced-usage.md)
- [Dashboard examples](docs/dashboards.md)
- [Contributing](CONTRIBUTING.md) and [development](docs/development.md)

## Support and license

Report reproducible issues on [GitHub](https://github.com/andrewtryder/ha-smart-oil-gauge/issues). This is an unofficial community project, not an official Connected Consumer Fuel product. See the [license](LICENSE).
