"""Data coordinator for the SA Fuel Pricing integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.dt import as_local, parse_datetime, utcnow

from .const import (
    API_BASE_URL,
    API_TIMEOUT,
    CONF_FUEL_TYPES,
    CONF_SELECTED_CITIES,
    CONF_SELECTED_SITES,
    CONF_SELECTED_SUBURBS,
    CONF_SUBSCRIBER_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PRICE_DIVISOR,
    PRICE_UNAVAILABLE,
    REFERENCE_DATA_UPDATE_INTERVAL,
    SA_COUNTRY_ID,
    SA_GEO_REGION_ID,
    SA_GEO_REGION_LEVEL,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass
class SiteDetail:
    """Represents a fuel station site."""

    site_id: int
    name: str
    address: str
    postcode: str
    brand_id: int
    brand_name: str
    latitude: float | None
    longitude: float | None
    suburb: str
    suburb_region_id: int  # G1 — used for suburb-level filtering
    city: str
    city_region_id: int  # G2 — used for city-level filtering
    last_modified: str


@dataclass
class SitePrice:
    """Represents a fuel price at a specific site."""

    site_id: int
    fuel_id: int
    fuel_name: str
    price_raw: float  # tenths of a cent
    transaction_date_utc: str
    collection_method: str

    @property
    def price_dollars(self) -> float | None:
        """Return price in AUD/L, or None if unavailable."""
        if self.price_raw >= PRICE_UNAVAILABLE:
            return None
        return round(self.price_raw / PRICE_DIVISOR, 3)

    @property
    def last_updated_local(self) -> datetime | None:
        """Return the transaction date as a local datetime."""
        try:
            dt = parse_datetime(self.transaction_date_utc)
            if dt is None:
                return None
            return as_local(dt)
        except (ValueError, TypeError):
            return None


@dataclass
class SAFuelData:
    """All coordinator data in one place."""

    # Keyed by site_id -> SiteDetail
    sites: dict[int, SiteDetail] = field(default_factory=dict)
    # Keyed by site_id -> fuel_id -> SitePrice
    prices: dict[int, dict[int, SitePrice]] = field(default_factory=dict)
    # Keyed by brand_id -> brand name
    brands: dict[int, str] = field(default_factory=dict)
    # Keyed by fuel_id -> fuel name
    fuel_types: dict[int, str] = field(default_factory=dict)
    # Keyed by (geo_region_level, geo_region_id) -> region name
    geo_regions: dict[tuple[int, int], str] = field(default_factory=dict)


class SAFuelAPIClient:
    """Async HTTP client for the SAFPIS API."""

    def __init__(self, session: aiohttp.ClientSession, subscriber_token: str) -> None:
        """Initialise with an aiohttp session and subscriber token."""
        self._session = session
        self._headers = {
            "Authorization": f"FPDAPI SubscriberToken={subscriber_token}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str) -> Any:
        """Perform an authenticated GET request."""
        url = f"{API_BASE_URL}{path}"
        try:
            async with asyncio.timeout(API_TIMEOUT):
                async with self._session.get(url, headers=self._headers) as response:
                    response.raise_for_status()
                    return await response.json()
        except TimeoutError as err:
            raise UpdateFailed(f"Timeout calling SAFPIS API: {url}") from err
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(
                    f"SAFPIS API authentication failed (HTTP {err.status})"
                ) from err
            raise UpdateFailed(
                f"SAFPIS API returned HTTP {err.status} for {url}: {err.message}"
            ) from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with SAFPIS API: {err}") from err

    async def get_brands(self) -> dict[int, str]:
        """Fetch all brands. Returns brand_id -> name."""
        data = await self._get(
            f"/Subscriber/GetCountryBrands?countryId={SA_COUNTRY_ID}"
        )
        return {b["BrandId"]: b["Name"] for b in data.get("Brands", [])}

    async def get_fuel_types(self) -> dict[int, str]:
        """Fetch all fuel types. Returns fuel_id -> name."""
        data = await self._get(
            f"/Subscriber/GetCountryFuelTypes?countryId={SA_COUNTRY_ID}"
        )
        return {f["FuelId"]: f["Name"] for f in data.get("Fuels", [])}

    async def get_geo_regions(self) -> dict[tuple[int, int], str]:
        """Fetch all geographic regions. Returns (level, id) -> name."""
        data = await self._get(
            f"/Subscriber/GetCountryGeographicRegions?countryId={SA_COUNTRY_ID}"
        )
        return {
            (r["GeoRegionLevel"], r["GeoRegionId"]): r["Name"]
            for r in data.get("GeographicRegions", [])
        }

    async def get_site_details(
        self, geo_regions: dict[tuple[int, int], str], brands: dict[int, str]
    ) -> dict[int, SiteDetail]:
        """Fetch all SA site details. Returns site_id -> SiteDetail."""
        data = await self._get(
            f"/Subscriber/GetFullSiteDetails"
            f"?countryId={SA_COUNTRY_ID}"
            f"&geoRegionLevel={SA_GEO_REGION_LEVEL}"
            f"&geoRegionId={SA_GEO_REGION_ID}"
        )
        sites: dict[int, SiteDetail] = {}
        for s in data.get("S", []):
            site_id = s["S"]
            brand_id = s.get("B", 0)
            g1 = s.get("G1", 0)
            g2 = s.get("G2", 0)
            suburb = geo_regions.get((1, g1), "")
            city = geo_regions.get((2, g2), "")
            sites[site_id] = SiteDetail(
                site_id=site_id,
                name=s.get("N", "Unknown"),
                address=s.get("A", ""),
                postcode=s.get("P", ""),
                brand_id=brand_id,
                brand_name=brands.get(brand_id, "Unknown"),
                latitude=s.get("Lat"),
                longitude=s.get("Lng"),
                suburb=suburb,
                suburb_region_id=g1,
                city=city,
                city_region_id=g2,
                last_modified=s.get("M", ""),
            )
        return sites

    async def get_site_prices(
        self, fuel_types: dict[int, str]
    ) -> dict[int, dict[int, SitePrice]]:
        """Fetch all SA site prices. Returns site_id -> fuel_id -> SitePrice."""
        data = await self._get(
            f"/Price/GetSitesPrices"
            f"?countryId={SA_COUNTRY_ID}"
            f"&geoRegionLevel={SA_GEO_REGION_LEVEL}"
            f"&geoRegionId={SA_GEO_REGION_ID}"
        )
        prices: dict[int, dict[int, SitePrice]] = {}
        for p in data.get("SitePrices", []):
            site_id = p["SiteId"]
            fuel_id = p["FuelId"]
            if site_id not in prices:
                prices[site_id] = {}
            prices[site_id][fuel_id] = SitePrice(
                site_id=site_id,
                fuel_id=fuel_id,
                fuel_name=fuel_types.get(fuel_id, f"Fuel {fuel_id}"),
                price_raw=p.get("Price", PRICE_UNAVAILABLE),
                transaction_date_utc=p.get("TransactionDateUtc", ""),
                collection_method=p.get("CollectionMethod", "T"),
            )
        return prices


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
        # Hierarchical filter: most specific selection takes precedence.
        # Priority: Individual Sites > Suburbs > Cities > All Sites.
        # If individual sites are selected, only those are included (suburbs/cities ignored).
        active_site_ids: set[int] | None = None  # None = no filter = all sites

        if self._selected_cities or self._selected_suburbs or self._selected_sites:
            active_site_ids = set()
            selected_city_set = set(self._selected_cities)
            selected_suburb_set = set(self._selected_suburbs)
            selected_site_set = set(self._selected_sites)

            if selected_site_set:
                # Individual sites selected - use ONLY those
                for site_id in selected_site_set:
                    if site_id in sites:
                        active_site_ids.add(site_id)
            elif selected_suburb_set:
                # No individual sites, but suburbs selected - use ONLY suburb sites
                for site_id, site in sites.items():
                    if site.suburb_region_id in selected_suburb_set:
                        active_site_ids.add(site_id)
            elif selected_city_set:
                # No sites/suburbs, but cities selected - use ONLY city sites
                for site_id, site in sites.items():
                    if site.city_region_id in selected_city_set:
                        active_site_ids.add(site_id)

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
                identifiers={(DOMAIN, f"sa_fuel_{stale_id}")}
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
