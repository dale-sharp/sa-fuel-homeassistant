"""Tests for SAFuelDataCoordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sa_fuel_pricing.const import (
    CONF_FUEL_TYPES,
    CONF_SELECTED_CITIES,
    CONF_SELECTED_SITES,
    CONF_SELECTED_SUBURBS,
    CONF_SUBSCRIBER_TOKEN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEVICE_IDENTIFIER_PREFIX,
    DOMAIN,
)
from custom_components.sa_fuel_pricing.coordinator import (
    SAFuelData,
    SAFuelDataCoordinator,
)

from .conftest import (
    PRICE_A_ULP,
    TEST_BRANDS,
    TEST_FUEL_TYPES,
    TEST_GEO_REGIONS,
    TEST_SITES,
)


def _make_coordinator(hass, **option_overrides):
    """Create a coordinator with custom options without touching the default config_entry fixture."""
    opts = {
        CONF_SELECTED_CITIES: [],
        CONF_SELECTED_SUBURBS: [],
        CONF_SELECTED_SITES: [],
        CONF_FUEL_TYPES: [2, 3, 5, 12],
        "scan_interval": DEFAULT_SCAN_INTERVAL_MINUTES,
        **option_overrides,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SUBSCRIBER_TOKEN: "test-token"},
        options=opts,
    )
    entry.add_to_hass(hass)
    return SAFuelDataCoordinator(hass, entry)


# --- Reference data refresh ---


async def test_first_fetch_calls_all_reference_endpoints(
    hass, coordinator, mock_api_client
):
    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()

    mock_api_client.get_brands.assert_called_once()
    mock_api_client.get_fuel_types.assert_called_once()
    mock_api_client.get_geo_regions.assert_called_once()
    mock_api_client.get_site_details.assert_called_once()
    mock_api_client.get_site_prices.assert_called_once()


async def test_second_fetch_within_24h_skips_reference_endpoints(
    hass, coordinator, mock_api_client
):
    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()
        for attr in (
            "get_brands",
            "get_fuel_types",
            "get_geo_regions",
            "get_site_details",
        ):
            getattr(mock_api_client, attr).reset_mock()
        mock_api_client.get_site_prices.reset_mock()

        await coordinator.async_refresh()

    mock_api_client.get_brands.assert_not_called()
    mock_api_client.get_fuel_types.assert_not_called()
    mock_api_client.get_geo_regions.assert_not_called()
    mock_api_client.get_site_details.assert_not_called()
    mock_api_client.get_site_prices.assert_called_once()


async def test_fetch_after_24h_calls_reference_endpoints_again(
    hass, coordinator, mock_api_client
):
    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()
        coordinator._last_reference_refresh -= timedelta(hours=25)
        mock_api_client.get_brands.reset_mock()

        await coordinator.async_refresh()

    mock_api_client.get_brands.assert_called_once()


# --- Site filtering ---


async def test_no_filter_returns_all_sites(hass, coordinator, mock_api_client):
    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()

    assert set(coordinator.data.prices.keys()) == {61205460, 61501009, 61501012}


async def test_city_filter_returns_only_city_sites(hass, mock_api_client):
    coord = _make_coordinator(hass, **{CONF_SELECTED_CITIES: [189]})  # Adelaide only
    with patch.object(coord, "get_api", return_value=mock_api_client):
        await coord.async_refresh()

    # Only Site A (OTR Dry Creek) is in Adelaide (city_region_id=189)
    assert set(coord.data.prices.keys()) == {61205460}


async def test_suburb_overrides_city_filter(hass, mock_api_client):
    # Both cities selected, but only Dry Creek suburb — city Barossa must be excluded
    coord = _make_coordinator(
        hass,
        **{CONF_SELECTED_CITIES: [189, 190], CONF_SELECTED_SUBURBS: [170227225]},
    )
    with patch.object(coord, "get_api", return_value=mock_api_client):
        await coord.async_refresh()

    # Only Site A is in Dry Creek (suburb_region_id=170227225)
    assert set(coord.data.prices.keys()) == {61205460}


async def test_site_overrides_suburb_filter(hass, mock_api_client):
    # Both suburbs selected, but only Site A individually picked — Site B and C must be excluded
    coord = _make_coordinator(
        hass,
        **{
            CONF_SELECTED_SUBURBS: [170227225, 170227300],
            CONF_SELECTED_SITES: [61205460],
        },
    )
    with patch.object(coord, "get_api", return_value=mock_api_client):
        await coord.async_refresh()

    assert set(coord.data.prices.keys()) == {61205460}


async def test_unknown_site_id_in_selection_returns_empty(hass, mock_api_client):
    coord = _make_coordinator(hass, **{CONF_SELECTED_SITES: [99999]})
    with patch.object(coord, "get_api", return_value=mock_api_client):
        await coord.async_refresh()

    assert coord.data.prices == {}


# --- Fuel type filtering ---


async def test_fuel_type_filter_excludes_unselected_types(hass, mock_api_client):
    coord = _make_coordinator(hass, **{CONF_FUEL_TYPES: [2]})  # ULP only
    with patch.object(coord, "get_api", return_value=mock_api_client):
        await coord.async_refresh()

    for site_prices in coord.data.prices.values():
        assert all(fid == 2 for fid in site_prices)


async def test_empty_fuel_selection_returns_all_types(hass, mock_api_client):
    coord = _make_coordinator(hass, **{CONF_FUEL_TYPES: []})
    with patch.object(coord, "get_api", return_value=mock_api_client):
        await coord.async_refresh()

    # Site C should include both E10 (12) and ULSD (6)
    assert 6 in coord.data.prices[61501012]
    assert 12 in coord.data.prices[61501012]


# --- Price sentinel ---


async def test_sentinel_price_creates_site_price_with_none_dollars(
    hass, coordinator, mock_api_client
):
    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()

    # Site A Diesel has Price: 9999
    diesel_price = coordinator.data.prices[61205460][3]
    assert diesel_price.price_raw == 9999.0
    assert diesel_price.price_dollars is None


# --- Stale device removal ---


async def test_stale_device_removed_when_site_drops_from_prices(
    hass, coordinator, mock_api_client
):
    # Pre-register a device for Site B so the coordinator can remove it
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=coordinator._entry.entry_id,
        identifiers={(DOMAIN, f"{DEVICE_IDENTIFIER_PREFIX}61501009")},
        name="BP Nuriootpa",
    )

    # First update: all three sites
    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()

    # Second update: Site B vanishes from prices
    prices_without_b = {
        61205460: {2: PRICE_A_ULP},
        61501012: {12: coordinator.data.prices[61501012][12]},
    }
    mock_api_client.get_site_prices = AsyncMock(return_value=prices_without_b)
    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{DEVICE_IDENTIFIER_PREFIX}61501009")}
    )
    assert device is None


# --- Stash mechanism ---


async def test_reference_snapshot_excludes_prices(hass, coordinator, mock_api_client):
    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()

    snapshot = coordinator.reference_snapshot()
    assert snapshot.prices == {}
    assert snapshot.sites == TEST_SITES


async def test_restore_stash_skips_reference_calls_on_next_refresh(
    hass, coordinator, mock_api_client
):
    stash = SAFuelData(
        sites=TEST_SITES,
        brands=TEST_BRANDS,
        fuel_types=TEST_FUEL_TYPES,
        geo_regions=TEST_GEO_REGIONS,
    )
    coordinator.restore_reference_stash(stash)

    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()

    mock_api_client.get_brands.assert_not_called()
    mock_api_client.get_site_prices.assert_called_once()


# --- Error handling ---


async def test_update_failed_propagates(hass, coordinator, mock_api_client, caplog):
    mock_api_client.get_site_prices = AsyncMock(side_effect=UpdateFailed("boom"))
    with patch.object(coordinator, "get_api", return_value=mock_api_client):
        await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert "Error fetching sa_fuel_pricing data" in caplog.text


async def test_config_entry_auth_failed_propagates(hass, coordinator, mock_api_client):
    mock_api_client.get_brands = AsyncMock(side_effect=ConfigEntryAuthFailed("401"))
    with (
        patch.object(coordinator, "get_api", return_value=mock_api_client),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await coordinator._async_update_data()
