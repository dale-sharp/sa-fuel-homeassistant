"""API client and data models for the SA Fuel Pricing integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util.dt import as_local, parse_datetime

from .const import (
    API_BASE_URL,
    API_TIMEOUT,
    PRICE_DIVISOR,
    PRICE_UNAVAILABLE,
    SA_COUNTRY_ID,
    SA_GEO_REGION_ID,
    SA_GEO_REGION_LEVEL,
)

if TYPE_CHECKING:
    from datetime import datetime


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
        except ValueError, TypeError:
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
