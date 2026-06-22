![logo](https://github.com/dale-sharp/sa-fuel-homeassistant/blob/main/custom_components/sa_fuel_pricing/brand/logo.png)

# SA Fuel Pricing

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Validate](https://github.com/dale-sharp/sa-fuel-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/dale-sharp/sa-fuel-homeassistant/actions/workflows/validate.yml)
[![Lint](https://github.com/dale-sharp/sa-fuel-homeassistant/actions/workflows/lint.yml/badge.svg)](https://github.com/dale-sharp/sa-fuel-homeassistant/actions/workflows/lint.yml)

A [Home Assistant](https://www.home-assistant.io/) integration that brings South Australian fuel prices into your home via the [SAFPIS (South Australian Fuel Pricing Information Scheme)](https://www.safuelpricinginformation.com.au/) API.

Each fuel station appears as a **device**. Each fuel type available at that station becomes a **sensor** showing the current price in **AUD/L**, updated as frequently as every minute.

---

## Requirements

- Home Assistant 2024.1.0 or newer
- A SAFPIS Data Publisher subscriber token — register at [safuelpricinginformation.com.au](https://www.safuelpricinginformation.com.au/publishers.html)

---

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations** → click the three-dot menu → **Custom repositories**
2. Add `https://github.com/dale-sharp/sa-fuel-homeassistant` with category **Integration**
3. Search for **SA Fuel Pricing** and install it
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/sa_fuel_pricing/` directory into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **SA Fuel Pricing**
3. Work through the five-step setup wizard:

| Step | What you do |
|---|---|
| **1. Token** | Enter your SAFPIS subscriber token — validated against the API immediately |
| **2. Cities** | Pick one or more SA cities, or leave blank for all (~715 stations across 83 cities) |
| **3. Suburbs** | Optionally narrow to specific suburbs within your chosen cities |
| **4. Stations** | Optionally pin to individual stations within your chosen suburbs |
| **5. Fuel types & polling** | Choose which fuel types to track and how often to poll (1–60 min, default 5 min) |

All steps after the first are optional — you can leave any of them blank to include everything at that level.

---

## Entities

Each tracked fuel station becomes a **device** in Home Assistant. Within that device, one **sensor entity** is created per fuel type:

| Fuel type | Translation key | Enabled by default |
|---|---|---|
| Unleaded (ULP) | `unleaded` | ✅ |
| Diesel | `diesel` | ✅ |
| Premium Unleaded 95 | `premium_95` | ✅ |
| Premium Unleaded 98 | `premium_98` | ✅ |
| E10 | `e10` | ✅ |
| Premium Diesel | `premium_diesel` | ✅ |
| LPG | `lpg` | ❌ (enable in entity registry if needed) |
| E85 | `e85` | ❌ (enable in entity registry if needed) |

### Sensor attributes

Each sensor exposes the following state attributes:

| Attribute | Description |
|---|---|
| `site_id` | SAFPIS site identifier |
| `site_name` | Station name |
| `site_address` | Street address |
| `postcode` | Postcode |
| `brand` | Fuel brand (e.g. On the Run, BP, Ampol) |
| `suburb` | Suburb name |
| `city` | City/region name |
| `latitude` / `longitude` | Station coordinates |
| `fuel_type` | Fuel type name |
| `last_updated` | Timestamp of the last price change (local time) |
| `unavailable` | `true` if the fuel type is not currently stocked at this station |

### Price

State value is in **AUD/L** (e.g. `1.579`). A value is reported to 3 decimal places. If a fuel type is listed as unavailable by the API (price code `9999`), the sensor state is `None` and `unavailable: true` is set in attributes.

---

## Data update behaviour

| Data type | Update frequency |
|---|---|
| Fuel prices | Every poll interval (default 5 min, configurable 1–60 min) |
| Station details, brands, geo regions | Once every 24 hours |

Reference data (station names, addresses, brands, geographic regions) is cached for 24 hours and carried across integration reloads to avoid unnecessary API calls. The SAFPIS API asks that prices are not polled more than once per minute.

---

## Reconfiguration

After setup you can adjust your configuration at any time:

- **Options** (gear icon on the integration card) — re-run the city/suburb/station/fuel wizard with your current selections pre-populated
- **Reconfigure** — replace your subscriber token (e.g. if it was rotated), must be the same SAFPIS account
- **Re-authenticate** — triggered automatically if the API returns a 401; prompts for a new token

---

## Dynamic updates

New fuel stations that appear in the API are automatically added as devices on the next poll. Stations that disappear (e.g. permanently closed) are automatically removed from the device registry. You can also manually delete a device from its device page — the delete button is enabled for any station that no longer has active prices.

---

## Contributing

Pull requests are welcome. The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting — run `ruff check .` and `ruff format .` before submitting. CI runs automatically on every pull request via GitHub Actions.

---

## Licence

See [LICENSE](LICENSE).
