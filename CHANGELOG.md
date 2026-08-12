# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.10] - 2026-08-12

### Changed

- Raised the minimum supported Home Assistant version to 2026.3.0, Home Assistant core's
  first release built on Python 3.14. 1.1.9's toolchain migration made `ruff format` emit
  PEP 758's unparenthesized multi-exception `except` syntax in `api.py`/`config_flow.py`;
  any earlier HA version runs on an older Python that cannot parse that syntax at all.
- Added a one-line copyright notice to the top of every shipped module (no behavior
  change), to satisfy ruff's `CPY001` rule — part of this repo's `select = ["ALL"]`
  ruleset, newly stabilized out of preview upstream and previously unenforced.

## [1.1.9] - 2026-07-22

### Changed

- Migrated the toolchain (devcontainer, `ruff`, `ty`, `requires-python`) from Python
  3.13 to 3.14, and removed `requires-python`'s upper bound entirely. Home Assistant
  core dropped Python 3.13 support in its recent releases, which had silently frozen
  this repo's `homeassistant`/`pytest-homeassistant-custom-component`/`aiohttp`
  Dependabot updates for roughly 5 months — no update PR for that group had been
  possible since the version cap made every newer release mathematically
  unresolvable. Matches the devcontainer/`requires-python`-only precedent set by #25.
- `ruff format` now emits Python 3.14's PEP 758 unparenthesized multi-exception
  `except` syntax (e.g. `except ValueError, TypeError:`), applied automatically to
  `api.py` and `config_flow.py` by the `target-version = "py314"` bump. Verified this
  syntax is valid and correctly behaves as expected under Python 3.14.6 before
  accepting the change — it's new syntax added by PEP 758, not the removed Python 2
  form it superficially resembles.

## [1.1.8] - 2026-07-22

### Fixed

- Fixed #43: config entry uniqueness detection for the SAFPIS subscriber token is now
  case-insensitive. Re-entering the same token with different letter casing is now
  correctly caught as a duplicate (during initial setup) or the same account (during
  reconfigure), instead of silently creating a redundant second config entry. Found by
  the adversarial Quality Scale re-review in #40.

## [1.1.7] - 2026-07-22

### Added

- Fixed #31: a Home Assistant repair issue is now raised after 3 consecutive
  SAFPIS API fetch failures, and automatically cleared on the next successful
  update. The issue is scoped per config entry (supports multiple SAFPIS
  accounts) and names the affected entry in its description. Authentication
  failures are excluded — those already trigger Home Assistant's own reauth
  flow.

## [1.1.6] - 2026-07-22

### Changed

- Split `coordinator.py` into `api.py` (data models `SiteDetail`/`SitePrice`/`SAFuelData`
  and the `SAFuelAPIClient` HTTP client) and a trimmed `coordinator.py`
  (`SAFuelDataCoordinator` only), matching `free-games-homeassistant`'s own module
  boundary. No behavior change — pure internal reorganization.

## [1.1.5] - 2026-07-22

### Fixed

- Fixed #25: a Linux-only test teardown `TypeError` in the DNS-resolver mock, caused by
  native Windows dev silently testing against a ~1-year-stale `homeassistant` release (a
  Python-3.13.2 resolution-fork threshold kept Windows on `2025.4.4` while CI/devcontainer
  already tracked current). Root-caused by dropping native-Windows dev/test support
  entirely — the devcontainer is now the only supported path, matching the same decision
  already made in the sibling `free-games-homeassistant` repo.

### Changed

- Removed the `pymicro-vad`/`pyspeex-noise` Windows-only dependency override and narrowed
  `requires-python` to `>=3.13.2,<3.14` (matching the devcontainer's actual Python version);
  `uv.lock` now resolves a single, unforked `homeassistant` version everywhere.
- Simplified `tests/conftest.py`'s event-loop/DNS-resolver fixtures — removed all
  Windows-specific branching, no longer needed.

## [1.1.4] - 2026-06-27

### Added

- Comprehensive pytest test suite covering data models, coordinator, config flow, options
  flow, sensors, and diagnostics (58 tests). Error-path tests assert expected log messages
  via `caplog`; test output is kept clean by suppressing expected log noise from the HA
  loader and integration debug messages.
- `DEVICE_IDENTIFIER_PREFIX` constant in `const.py` to eliminate duplicated `"sa_fuel_"`
  string across `entity.py`, `__init__.py`, and `coordinator.py`.
- Shared schema-builder functions (`_cities_schema`, `_suburbs_schema`, `_sites_schema`,
  `_fuel_types_schema`) in `config_flow.py` to remove duplication between config and
  options flows.

### Fixed

- Replaced `assert self._ref is not None` guards in config and options flow step methods
  with `async_abort(reason="unknown")`, which is safe under Python's optimised mode (`-O`).
- Removed unused `asyncio.gather` wrapper in `async_step_init` of the options flow.
- Removed `_KNOWN_FUEL_NAMES` dict from `config_flow.py`; fuel name fallback now uses
  `f"Fuel {fid}"` sourced from the API response.

---

## [1.1.3] - 2026-06-24

### Added

- Version bump for removing brand ignore from HACS validation Action

---

## [1.1.2] - 2026-06-24

### Added

- Brand assets (`brand/dark_icon.png` and `brand/dark_logo.png`) for display in HACS and
  the Home Assistant integrations gallery.

---

## [1.1.1] - 2026-06-23

### Added

- Brand assets (`brand/icon.png` and `brand/logo.png`) for display in HACS and the
  Home Assistant integrations gallery.

---

## [1.1.0] - 2026-06-20

### Fixed

- **BREAKING** - Site selection filter now uses hierarchical precedence instead of additive
  (union) behavior. The most specific level of selection takes exclusive precedence:
  - Individual sites selected - ONLY those sites are included (suburb/city selections ignored)
  - Suburbs selected, no individual sites - ONLY sites within those suburbs (city selections ignored)
  - Cities selected, no suburbs or individual sites - ONLY sites within those cities
  - Nothing selected - all sites (unchanged)

  Previously, selecting any combination of cities, suburbs, and individual sites returned
  the union of all matching sites. For example, selecting City=Adelaide and one individual
  site in Kent Town would return that site PLUS every other site in Adelaide.

  **Impact**: Users who relied on the additive behavior may see devices and entities removed
  from Home Assistant after upgrading. Reconfigure the integration via
  Settings > Devices & Services > SA Fuel Pricing > Configure to re-select the desired sites.

### Changed

- Extracted site filter logic from `_async_update_data()` into a dedicated
  `_resolve_active_site_ids()` helper method. No behaviour change - internal refactor only.

---

## [1.0.1] - 2026-06-19

### Fixed

- Release workflow packaging now correctly structures the zip file for HACS installation.
  The zip archive now contains `__init__.py`, `manifest.json`, etc. at its root so that
  HACS extracts files directly into `custom_components/sa_fuel_pricing/` without path
  duplication.

---

## [1.0.0] - 2026-06-19

### Added

- Initial release of the SA Fuel Pricing integration.
- Five-step configuration wizard: subscriber token validation, city selection, suburb
  selection, individual site selection, and fuel type and polling interval selection.
- `DataUpdateCoordinator` polling the SAFPIS API with configurable interval (1-60 min,
  default 5 min) and 24-hour reference data caching (brands, fuel types, geo regions,
  sites).
- One Home Assistant device per tracked fuel station; one sensor entity per available fuel
  type showing the current price in AUD/L.
- Supported fuel types: Unleaded (ULP), Diesel, Premium 95, Premium 98, E10, Premium
  Diesel, LPG, E85.
- Automatic dynamic device and entity discovery on each coordinator refresh.
- Automatic stale device removal when a site no longer matches the active filter.
- Reauthentication flow, reconfiguration (options) flow.
- Diagnostics support with subscriber token redacted.
- GitHub Actions workflows: HACS validation, hassfest, Ruff lint, and release packaging.
