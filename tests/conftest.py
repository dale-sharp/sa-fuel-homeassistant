"""Shared test fixtures for SA Fuel Pricing tests."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sa_fuel_pricing.const import (
    CONF_FUEL_TYPES,
    CONF_SELECTED_CITIES,
    CONF_SELECTED_SITES,
    CONF_SELECTED_SUBURBS,
    CONF_SUBSCRIBER_TOKEN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from custom_components.sa_fuel_pricing.coordinator import (
    SAFuelData,
    SAFuelDataCoordinator,
    SiteDetail,
    SitePrice,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file by name."""
    return json.loads((FIXTURES_DIR / name).read_text())


# ---------------------------------------------------------------------------
# Canonical test data — Python objects matching tests/fixtures/*.json
# ---------------------------------------------------------------------------

SITE_A = SiteDetail(
    site_id=61205460,
    name="OTR Dry Creek",
    address="17 Vater St",
    postcode="5094",
    brand_id=169,
    brand_name="On the Run",
    latitude=-34.819,
    longitude=138.592,
    suburb="Dry Creek",
    suburb_region_id=170227225,
    city="Adelaide",
    city_region_id=189,
    last_modified="2025-04-11T01:23:01.397",
)

SITE_B = SiteDetail(
    site_id=61501009,
    name="BP Nuriootpa",
    address="20 Murray St",
    postcode="5355",
    brand_id=5,
    brand_name="BP",
    latitude=-34.470,
    longitude=138.993,
    suburb="Nuriootpa",
    suburb_region_id=170227300,
    city="Barossa",
    city_region_id=190,
    last_modified="2025-04-11T01:23:01.397",
)

SITE_C = SiteDetail(
    site_id=61501012,
    name="OTR Nuriootpa",
    address="5 Research Rd",
    postcode="5355",
    brand_id=169,
    brand_name="On the Run",
    latitude=None,
    longitude=None,
    suburb="Nuriootpa",
    suburb_region_id=170227300,
    city="Barossa",
    city_region_id=190,
    last_modified="2025-04-11T01:23:01.397",
)

PRICE_A_ULP = SitePrice(
    site_id=61205460,
    fuel_id=2,
    fuel_name="Unleaded",
    price_raw=1579.0,
    transaction_date_utc="2026-06-18T03:31:00",
    collection_method="T",
)
PRICE_A_DIESEL = SitePrice(
    site_id=61205460,
    fuel_id=3,
    fuel_name="Diesel",
    price_raw=9999.0,
    transaction_date_utc="2026-06-18T03:31:00",
    collection_method="T",
)
PRICE_B_ULP = SitePrice(
    site_id=61501009,
    fuel_id=2,
    fuel_name="Unleaded",
    price_raw=1599.0,
    transaction_date_utc="2026-06-18T03:29:00",
    collection_method="T",
)
PRICE_B_P95 = SitePrice(
    site_id=61501009,
    fuel_id=5,
    fuel_name="Premium Unleaded 95",
    price_raw=1799.0,
    transaction_date_utc="2026-06-18T03:29:00",
    collection_method="T",
)
PRICE_C_E10 = SitePrice(
    site_id=61501012,
    fuel_id=12,
    fuel_name="E10",
    price_raw=1450.0,
    transaction_date_utc="2026-06-18T01:41:15",
    collection_method="T",
)
PRICE_C_ULSD = SitePrice(
    site_id=61501012,
    fuel_id=6,
    fuel_name="ULSD",
    price_raw=1350.0,
    transaction_date_utc="2026-06-18T01:41:15",
    collection_method="T",
)

TEST_SITES: dict = {s.site_id: s for s in (SITE_A, SITE_B, SITE_C)}
TEST_PRICES: dict = {
    61205460: {2: PRICE_A_ULP, 3: PRICE_A_DIESEL},
    61501009: {2: PRICE_B_ULP, 5: PRICE_B_P95},
    61501012: {12: PRICE_C_E10, 6: PRICE_C_ULSD},
}
TEST_BRANDS: dict = {169: "On the Run", 5: "BP"}
TEST_FUEL_TYPES: dict = {
    2: "Unleaded",
    3: "Diesel",
    5: "Premium Unleaded 95",
    12: "E10",
    6: "ULSD",
}
TEST_GEO_REGIONS: dict = {
    (2, 189): "Adelaide",
    (2, 190): "Barossa",
    (1, 170227225): "Dry Creek",
    (1, 170227300): "Nuriootpa",
}

TEST_DATA = SAFuelData(
    sites=TEST_SITES,
    prices=TEST_PRICES,
    brands=TEST_BRANDS,
    fuel_types=TEST_FUEL_TYPES,
    geo_regions=TEST_GEO_REGIONS,
)


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """MockConfigEntry with no site/city/suburb filter and all 4 SA fuel types."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SUBSCRIBER_TOKEN: "2FEB37D3-0000-0000-0000-000000000001"},
        options={
            CONF_FUEL_TYPES: [2, 3, 5, 12],
            CONF_SELECTED_CITIES: [],
            CONF_SELECTED_SUBURBS: [],
            CONF_SELECTED_SITES: [],
            "scan_interval": DEFAULT_SCAN_INTERVAL_MINUTES,
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def coordinator(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> SAFuelDataCoordinator:
    """SAFuelDataCoordinator bound to hass but with no real API calls."""
    return SAFuelDataCoordinator(hass, config_entry)


@pytest.fixture
def mock_api_client() -> MagicMock:
    """Pre-configured AsyncMock for SAFuelAPIClient returning test fixture data."""
    client = MagicMock()
    client.get_brands = AsyncMock(return_value=TEST_BRANDS)
    client.get_fuel_types = AsyncMock(return_value=TEST_FUEL_TYPES)
    client.get_geo_regions = AsyncMock(return_value=TEST_GEO_REGIONS)
    client.get_site_details = AsyncMock(return_value=TEST_SITES)
    client.get_site_prices = AsyncMock(return_value=TEST_PRICES)
    return client


# ---------------------------------------------------------------------------
# Windows asyncio compatibility
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="session")
def mock_zeroconf_resolver() -> Generator[MagicMock]:
    """Override the HA plugin's async session fixture with a synchronous version.

    On Windows, asyncio's ProactorEventLoop._make_self_pipe() calls
    socket.socketpair() using AF_INET, which is blocked by pytest-socket before
    session-scoped fixtures are initialised.  By replacing the async
    pytest_asyncio fixture with an ordinary synchronous one we eliminate the
    need for a session-scoped event loop (and therefore any socket creation)
    at session startup, while still patching the HA resolver so that async
    tests that import aiohttp internals don't hit the real DNS stack.
    """
    patcher = patch("homeassistant.helpers.aiohttp_client._async_make_resolver")
    patcher.start()
    try:
        yield patcher
    finally:
        patcher.stop()


@pytest.fixture(autouse=True)
def enable_event_loop_debug(request: pytest.FixtureRequest) -> None:
    """Enable asyncio debug mode — skipped on Windows to avoid socket-pair conflict."""
    if sys.platform != "win32":
        loop = request.getfixturevalue("event_loop")
        loop.set_debug(True)


@pytest.fixture(autouse=True)
def verify_cleanup(request: pytest.FixtureRequest) -> Generator:
    """Verify no tasks leak after each test.

    Skipped on Windows to avoid the socket-pair conflict with ProactorEventLoop.
    """
    yield
    if sys.platform != "win32":
        loop = request.getfixturevalue("event_loop")
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        if pending:
            pytest.fail(f"Test left {len(pending)} pending task(s): {pending!r}")
