"""The SA Fuel Pricing integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .coordinator import SAFuelData, SAFuelDataCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Typed config entry alias — runtime_data holds the coordinator.
type SAFuelConfigEntry = ConfigEntry[SAFuelDataCoordinator]

# Key used to stash reference data across option-triggered reloads so the new
# coordinator does not need to re-fetch brands/geo/sites from the API.
_STASH_KEY = "sa_fuel_pricing_reference_stash"


async def async_setup_entry(hass: HomeAssistant, entry: SAFuelConfigEntry) -> bool:
    """Set up SA Fuel Pricing from a config entry."""
    coordinator = SAFuelDataCoordinator(hass, entry)

    # If a previous coordinator left a reference-data stash (options reload),
    # hand it over so the new coordinator skips the 4 reference API calls.
    stash: SAFuelData | None = hass.data.pop(_STASH_KEY, None)
    if stash is not None:
        coordinator.restore_reference_stash(stash)
        _LOGGER.debug(
            "Restored SAFPIS reference data stash — skipping reference API calls"
        )

    # Fetch initial data — raises ConfigEntryNotReady on failure
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Register a listener to handle options updates (fuel types, scan interval)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SAFuelConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    _hass: HomeAssistant,
    entry: SAFuelConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """
    Allow manual removal of a device that is no longer active.

    Returns True (permit deletion) only if the device's site is not currently
    present in the coordinator's active price data.
    """
    coordinator: SAFuelDataCoordinator = entry.runtime_data
    if coordinator.data is None:
        return True

    # Extract the site_id from the device identifier (format: "sa_fuel_{site_id}")
    for domain, identifier in device_entry.identifiers:
        if domain == entry.domain and identifier.startswith("sa_fuel_"):
            try:
                site_id = int(identifier.removeprefix("sa_fuel_"))
            except ValueError:
                return True
            # Only allow deletion if the site has no active prices
            return site_id not in coordinator.data.prices

    return True


async def _async_update_listener(hass: HomeAssistant, entry: SAFuelConfigEntry) -> None:
    """Handle options update — stash reference data then reload."""
    coordinator: SAFuelDataCoordinator = entry.runtime_data
    if coordinator.data is not None:
        # Stash only the reference portion (sites, brands, fuel_types, geo_regions).
        # Prices are always re-fetched so they are intentionally excluded.
        hass.data[_STASH_KEY] = coordinator.reference_snapshot()

    await hass.config_entries.async_reload(entry.entry_id)
