"""Tests for SAFuelAPIClient JSON-parsing and error-mapping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sa_fuel_pricing.coordinator import SAFuelAPIClient

from .conftest import TEST_BRANDS, TEST_FUEL_TYPES, TEST_GEO_REGIONS, load_fixture


def _make_mock_session(fixture_name: str) -> MagicMock:
    """Return a mock aiohttp.ClientSession that yields the given fixture JSON."""
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=load_fixture(fixture_name))
    mock_response.raise_for_status = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_cm)
    return mock_session


def _make_error_session(status: int) -> MagicMock:
    """Return a mock session whose raise_for_status raises a ClientResponseError."""
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=aiohttp.ClientResponseError(None, None, status=status)
    )
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_cm)
    return mock_session


async def test_get_brands_parses_response():
    """get_brands() returns a brand_id -> name dict from the API JSON."""
    client = SAFuelAPIClient(_make_mock_session("api_brands.json"), "test-token")
    result = await client.get_brands()
    assert result == {169: "On the Run", 5: "BP"}


async def test_get_fuel_types_parses_response():
    """get_fuel_types() returns a fuel_id -> name dict from the API JSON."""
    client = SAFuelAPIClient(_make_mock_session("api_fuel_types.json"), "test-token")
    result = await client.get_fuel_types()
    assert result == {
        2: "Unleaded",
        3: "Diesel",
        5: "Premium Unleaded 95",
        12: "E10",
        6: "ULSD",
    }


async def test_get_site_details_parses_null_coordinates():
    """get_site_details() stores None for Lat/Lng when the API returns null."""
    client = SAFuelAPIClient(_make_mock_session("api_site_details.json"), "test-token")
    result = await client.get_site_details(TEST_GEO_REGIONS, TEST_BRANDS)
    site_c = result[61501012]
    assert site_c.latitude is None
    assert site_c.longitude is None


async def test_get_site_prices_sentinel_price():
    """A Price of 9999 maps to price_raw=9999.0 and price_dollars=None."""
    client = SAFuelAPIClient(_make_mock_session("api_site_prices.json"), "test-token")
    result = await client.get_site_prices(TEST_FUEL_TYPES)
    diesel = result[61205460][3]
    assert diesel.price_raw == 9999.0
    assert diesel.price_dollars is None


async def test_client_raises_auth_failed_on_401():
    """HTTP 401 from the API is translated to ConfigEntryAuthFailed."""
    client = SAFuelAPIClient(_make_error_session(401), "test-token")
    with pytest.raises(ConfigEntryAuthFailed):
        await client.get_brands()


async def test_client_raises_update_failed_on_other_http_error():
    """Non-auth HTTP errors (e.g. 500) are translated to UpdateFailed."""
    client = SAFuelAPIClient(_make_error_session(500), "test-token")
    with pytest.raises(UpdateFailed):
        await client.get_brands()
