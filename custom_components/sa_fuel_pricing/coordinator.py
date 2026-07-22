"""Data coordinator for the SA Fuel Pricing integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.dt import utcnow

from .api import SAFuelAPIClient, SAFuelData, SitePrice
from .const import (
    CONF_FUEL_TYPES,
    CONF_SELECTED_CITIES,
    CONF_SELECTED_SITES,
    CONF_SELECTED_SUBURBS,
    CONF_SUBSCRIBER_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_IDENTIFIER_PREFIX,
    DOMAIN,
    REFERENCE_DATA_UPDATE_INTERVAL,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class SAFuelDataCoordinator(DataUpdateCoordinator[SAFuelData]):
    """Coordinator that manages both price polling and daily reference data refresh."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialise the coordinator from the config entry."""
        self._entry = entry
        self._subscriber_token: str = entry.data[CONF_SUBSCRIBER_TOKEN]
        self._selected_fuel_ids: list[int] = entry.options.get(CONF_FUEL_TYPES, [])
        self._selected_cities: list[int] = entry.options.get(CONF_SELECTED_CITIES, [])
        self._selected_suburbs: list[int] = entry.options.get(CONF_SELECTED_SUBURBS, [])
        self._selected_sites: list[int] = entry.options.get(CONF_SELECTED_SITES, [])
        scan_interval_minutes: int = entry.options.get(
            CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds()) // 60
        )
        self._api: SAFuelAPIClient | None = None
        self._last_reference_refresh: datetime | None = None  # UTC
        # Tracks which (site_id, fuel_id) pairs have had entities created.
        # Used by sensor.py to detect new combos without re-scanning everything.
        self.tracked_entity_keys: set[tuple[int, int]] = set()

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval_minutes),
        )

    def get_api(self) -> SAFuelAPIClient:
        """Lazily initialise the API client (needs HA event loop)."""
        if self._api is None:
            session = async_get_clientsession(self.hass)
            self._api = SAFuelAPIClient(session, self._subscriber_token)
        return self._api

    def _reference_data_stale(self) -> bool:
        """Return True if reference data needs a refresh."""
        if self._last_reference_refresh is None:
            return True
        return (
            utcnow() - self._last_reference_refresh
        ) > REFERENCE_DATA_UPDATE_INTERVAL

    def _resolve_active_site_ids(self, sites: dict[int, Any]) -> set[int] | None:
        """
        Return the set of site IDs to include, or None for no filter.

        Hierarchical precedence - most specific selection wins:
        1. Individual sites selected -> ONLY those sites
        2. Suburbs selected (no sites) -> ONLY those suburb sites
        3. Cities selected (no sites/suburbs) -> ONLY those city sites
        4. Nothing selected -> None (all sites)
        """
        if not (
            self._selected_cities or self._selected_suburbs or self._selected_sites
        ):
            return None

        active: set[int] = set()
        selected_site_set = set(self._selected_sites)
        selected_suburb_set = set(self._selected_suburbs)
        selected_city_set = set(self._selected_cities)

        if selected_site_set:
            # Individual sites selected - use ONLY those
            for site_id in selected_site_set:
                if site_id in sites:
                    active.add(site_id)
        elif selected_suburb_set:
            # No individual sites, but suburbs selected - use ONLY suburb sites
            for site_id, site in sites.items():
                if site.suburb_region_id in selected_suburb_set:
                    active.add(site_id)
        elif selected_city_set:
            # No sites/suburbs, but cities selected - use ONLY city sites
            for site_id, site in sites.items():
                if site.city_region_id in selected_city_set:
                    active.add(site_id)

        return active

    async def _async_update_data(self) -> SAFuelData:
        """Fetch prices (always) and reference data (if stale)."""
        api = self.get_api()

        # Keep existing reference data if still fresh
        existing: SAFuelData | None = self.data

        try:
            if self._reference_data_stale() or existing is None:
                _LOGGER.debug(
                    "Refreshing SAFPIS reference data "
                    "(brands, fuel types, geo regions, sites)"
                )
                brands, fuel_type_map, geo_regions = await asyncio.gather(
                    api.get_brands(),
                    api.get_fuel_types(),
                    api.get_geo_regions(),
                )
                sites = await api.get_site_details(geo_regions, brands)
                self._last_reference_refresh = utcnow()
            else:
                brands = existing.brands
                fuel_type_map = existing.fuel_types
                geo_regions = existing.geo_regions
                sites = existing.sites

            # Always fetch fresh prices
            all_prices = await api.get_site_prices(fuel_type_map)
        except (UpdateFailed, ConfigEntryAuthFailed):
            raise
        except Exception as err:
            raise UpdateFailed(f"Unexpected error fetching SAFPIS data: {err}") from err

        # --- Site filter ---
        active_site_ids = self._resolve_active_site_ids(sites)

        # --- Fuel type + site filter ---
        selected_fuel_set = set(self._selected_fuel_ids)

        filtered_prices: dict[int, dict[int, SitePrice]] = {}
        for site_id, raw_fuel_prices in all_prices.items():
            # Skip site if it's not in the active site set
            if active_site_ids is not None and site_id not in active_site_ids:
                continue
            # Filter fuel types if the user chose a subset; otherwise keep all
            site_prices = (
                {
                    fid: price
                    for fid, price in raw_fuel_prices.items()
                    if fid in selected_fuel_set
                }
                if selected_fuel_set
                else dict(raw_fuel_prices)
            )
            if site_prices:
                filtered_prices[site_id] = site_prices

        # --- Stale device removal ---
        self._remove_stale_devices(filtered_prices)

        return SAFuelData(
            sites=sites,
            prices=filtered_prices,
            brands=brands,
            fuel_types=fuel_type_map,
            geo_regions=geo_regions,
        )

    def reference_snapshot(self) -> SAFuelData:
        """
        Return a reference-only snapshot of current data for stashing across reloads.

        Prices are intentionally excluded — they are always re-fetched fresh.
        """
        existing = self.data
        if existing is None:
            return SAFuelData()
        return SAFuelData(
            sites=existing.sites,
            brands=existing.brands,
            fuel_types=existing.fuel_types,
            geo_regions=existing.geo_regions,
        )

    def _remove_stale_devices(
        self, filtered_prices: dict[int, dict[int, SitePrice]]
    ) -> None:
        """Remove devices for sites that no longer appear in the filtered price data."""
        if self.data is None:
            return
        stale_site_ids = set(self.data.prices.keys()) - set(filtered_prices.keys())
        if not stale_site_ids:
            return
        device_registry = dr.async_get(self.hass)
        for stale_id in stale_site_ids:
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, f"{DEVICE_IDENTIFIER_PREFIX}{stale_id}")}
            )
            if device:
                _LOGGER.debug("Removing stale device for site_id %s", stale_id)
                device_registry.async_update_device(
                    device_id=device.id,
                    remove_config_entry_id=self._entry.entry_id,
                )

    def restore_reference_stash(self, stash: SAFuelData) -> None:
        """
        Pre-populate reference data from a previous coordinator instance.

        Sets the last-refresh timestamp to now so the new coordinator skips
        the reference API calls on its first _async_update_data invocation.
        """
        self.async_set_updated_data(stash)
        self._last_reference_refresh = utcnow()
