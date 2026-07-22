"""Tests for the SA Fuel Pricing integration's setup/unload/reload lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers import device_registry as dr

from custom_components.sa_fuel_pricing import (
    _STASH_KEY,
    PLATFORMS,
    _async_update_listener,
    async_remove_config_entry_device,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.sa_fuel_pricing.const import DEVICE_IDENTIFIER_PREFIX, DOMAIN
from custom_components.sa_fuel_pricing.coordinator import SAFuelData

from .conftest import (
    TEST_BRANDS,
    TEST_DATA,
    TEST_FUEL_TYPES,
    TEST_GEO_REGIONS,
    TEST_SITES,
)


def _mock_coordinator() -> MagicMock:
    """A MagicMock standing in for a freshly-constructed SAFuelDataCoordinator."""
    mock = MagicMock()
    mock.async_config_entry_first_refresh = AsyncMock()
    mock.restore_reference_stash = MagicMock()
    return mock


# --- async_setup_entry ---


async def test_setup_entry_happy_path(hass, config_entry):
    mock_coordinator = _mock_coordinator()

    with (
        patch(
            "custom_components.sa_fuel_pricing.SAFuelDataCoordinator",
            return_value=mock_coordinator,
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", AsyncMock()
        ) as mock_forward,
    ):
        result = await async_setup_entry(hass, config_entry)

    assert result is True
    mock_coordinator.async_config_entry_first_refresh.assert_called_once()
    mock_coordinator.restore_reference_stash.assert_not_called()
    assert config_entry.runtime_data is mock_coordinator
    mock_forward.assert_called_once_with(config_entry, PLATFORMS)


async def test_setup_entry_restores_stash_when_present(hass, config_entry):
    stash = SAFuelData(
        sites=TEST_SITES,
        brands=TEST_BRANDS,
        fuel_types=TEST_FUEL_TYPES,
        geo_regions=TEST_GEO_REGIONS,
    )
    hass.data[_STASH_KEY] = stash
    mock_coordinator = _mock_coordinator()

    with (
        patch(
            "custom_components.sa_fuel_pricing.SAFuelDataCoordinator",
            return_value=mock_coordinator,
        ),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
    ):
        await async_setup_entry(hass, config_entry)

    mock_coordinator.restore_reference_stash.assert_called_once_with(stash)
    assert _STASH_KEY not in hass.data


# --- async_unload_entry ---


async def test_unload_entry_delegates_to_unload_platforms(hass, config_entry):
    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    ) as mock_unload:
        result = await async_unload_entry(hass, config_entry)

    assert result is True
    mock_unload.assert_called_once_with(config_entry, PLATFORMS)


# --- async_remove_config_entry_device ---


async def test_remove_device_allowed_when_coordinator_data_is_none(
    hass, config_entry, coordinator
):
    config_entry.runtime_data = coordinator
    coordinator.data = None
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, f"{DEVICE_IDENTIFIER_PREFIX}61205460")},
        name="Test",
    )

    result = await async_remove_config_entry_device(hass, config_entry, device)
    assert result is True


async def test_remove_device_blocked_when_site_has_active_price(
    hass, config_entry, coordinator
):
    config_entry.runtime_data = coordinator
    coordinator.data = TEST_DATA  # site 61205460 has active prices
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, f"{DEVICE_IDENTIFIER_PREFIX}61205460")},
        name="Test",
    )

    result = await async_remove_config_entry_device(hass, config_entry, device)
    assert result is False


async def test_remove_device_allowed_when_site_has_no_active_price(
    hass, config_entry, coordinator
):
    config_entry.runtime_data = coordinator
    coordinator.data = SAFuelData(sites=TEST_SITES, prices={})
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, f"{DEVICE_IDENTIFIER_PREFIX}61205460")},
        name="Test",
    )

    result = await async_remove_config_entry_device(hass, config_entry, device)
    assert result is True


async def test_remove_device_allowed_when_identifier_domain_does_not_match(
    hass, config_entry, coordinator
):
    config_entry.runtime_data = coordinator
    coordinator.data = TEST_DATA
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("other_domain", "sa_fuel_61205460")},
        name="Test",
    )

    result = await async_remove_config_entry_device(hass, config_entry, device)
    assert result is True


async def test_remove_device_allowed_when_identifier_suffix_is_not_numeric(
    hass, config_entry, coordinator
):
    config_entry.runtime_data = coordinator
    coordinator.data = TEST_DATA
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, f"{DEVICE_IDENTIFIER_PREFIX}not-a-number")},
        name="Test",
    )

    result = await async_remove_config_entry_device(hass, config_entry, device)
    assert result is True


# --- _async_update_listener ---


async def test_update_listener_stashes_reference_data_and_reloads(
    hass, config_entry, coordinator
):
    config_entry.runtime_data = coordinator
    coordinator.data = TEST_DATA

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        await _async_update_listener(hass, config_entry)

    assert hass.data[_STASH_KEY].sites == TEST_DATA.sites
    assert hass.data[_STASH_KEY].prices == {}  # reference_snapshot excludes prices
    mock_reload.assert_called_once_with(config_entry.entry_id)


async def test_update_listener_skips_stash_when_coordinator_has_no_data(
    hass, config_entry, coordinator
):
    config_entry.runtime_data = coordinator
    coordinator.data = None

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        await _async_update_listener(hass, config_entry)

    assert _STASH_KEY not in hass.data
    mock_reload.assert_called_once_with(config_entry.entry_id)
