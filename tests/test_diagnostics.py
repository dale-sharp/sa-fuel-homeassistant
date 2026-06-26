"""Tests for async_get_config_entry_diagnostics."""

from __future__ import annotations

import json

from custom_components.sa_fuel_pricing.const import CONF_SUBSCRIBER_TOKEN
from custom_components.sa_fuel_pricing.coordinator import SAFuelData, SiteDetail
from custom_components.sa_fuel_pricing.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import TEST_DATA


async def test_subscriber_token_is_redacted(hass, config_entry, coordinator):
    config_entry.runtime_data = coordinator
    coordinator.data = TEST_DATA

    result = await async_get_config_entry_diagnostics(hass, config_entry)

    assert result["entry_data"][CONF_SUBSCRIBER_TOKEN] == "**REDACTED**"


async def test_top_level_keys_present(hass, config_entry, coordinator):
    config_entry.runtime_data = coordinator
    coordinator.data = TEST_DATA

    result = await async_get_config_entry_diagnostics(hass, config_entry)

    for key in ("entry_data", "options", "coordinator", "data_summary"):
        assert key in result, f"Missing top-level key: {key}"


async def test_sample_sites_capped_at_10(hass, config_entry, coordinator):
    # Create 15 identical sites with unique IDs
    big_sites = {
        i: SiteDetail(
            site_id=i,
            name=f"Site {i}",
            address="",
            postcode="",
            brand_id=1,
            brand_name="Test",
            latitude=None,
            longitude=None,
            suburb="",
            suburb_region_id=0,
            city="",
            city_region_id=0,
            last_modified="",
        )
        for i in range(1, 16)
    }
    config_entry.runtime_data = coordinator
    coordinator.data = SAFuelData(
        sites=big_sites,
        prices={i: {2: TEST_DATA.prices[61205460][2]} for i in range(1, 16)},
    )

    result = await async_get_config_entry_diagnostics(hass, config_entry)

    assert len(result["data_summary"]["sample_sites"]) <= 10


async def test_counts_are_correct(hass, config_entry, coordinator):
    config_entry.runtime_data = coordinator
    coordinator.data = TEST_DATA

    result = await async_get_config_entry_diagnostics(hass, config_entry)
    summary = result["data_summary"]

    assert summary["total_sites"] == 3
    assert summary["tracked_sites"] == 3
    assert summary["total_price_entries"] == 6  # 2+2+2


async def test_output_is_json_serialisable(hass, config_entry, coordinator):
    config_entry.runtime_data = coordinator
    coordinator.data = TEST_DATA

    result = await async_get_config_entry_diagnostics(hass, config_entry)

    # Will raise TypeError if any value is not JSON-serialisable
    json.dumps(result)
