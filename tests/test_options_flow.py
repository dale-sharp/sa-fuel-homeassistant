"""Tests for SAFuelPricingOptionsFlow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sa_fuel_pricing.config_flow import (
    _FlowReferenceData,
    _SiteSummary,
)
from custom_components.sa_fuel_pricing.const import (
    CONF_FUEL_TYPES,
    CONF_SELECTED_CITIES,
    CONF_SELECTED_SITES,
    CONF_SELECTED_SUBURBS,
    DOMAIN,
)

# Allow HA's loader to discover custom_components/sa_fuel_pricing during tests.
pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

_TEST_FUEL_TYPES = {2: "Unleaded", 3: "Diesel", 5: "Premium Unleaded 95", 12: "E10"}

_MOCK_REF = _FlowReferenceData(
    fuel_types=_TEST_FUEL_TYPES,
    cities={189: "Adelaide", 190: "Barossa"},
    suburbs={170227225: ("Dry Creek", 189), 170227300: ("Nuriootpa", 190)},
    sites={
        61205460: _SiteSummary(
            61205460,
            "OTR Dry Creek",
            "17 Vater St",
            189,
            "Adelaide",
            170227225,
            "Dry Creek",
        ),
        61501009: _SiteSummary(
            61501009,
            "BP Nuriootpa",
            "20 Murray St",
            190,
            "Barossa",
            170227300,
            "Nuriootpa",
        ),
    },
)


async def _open_options_flow(hass, config_entry):
    """Open the options flow and advance past async_step_init."""
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow._api_get",
            AsyncMock(
                return_value={
                    "Fuels": [
                        {"FuelId": k, "Name": v} for k, v in _TEST_FUEL_TYPES.items()
                    ]
                }
            ),
        ),
        patch(
            "custom_components.sa_fuel_pricing.config_flow._fetch_reference_data",
            AsyncMock(return_value=_MOCK_REF),
        ),
    ):
        return await hass.config_entries.options.async_init(config_entry.entry_id)


async def test_options_flow_opens_with_existing_cities_preselected(hass, config_entry):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_entry.data,
        options={**config_entry.options, CONF_SELECTED_CITIES: [189]},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow._api_get",
            AsyncMock(
                return_value={
                    "Fuels": [
                        {"FuelId": k, "Name": v} for k, v in _TEST_FUEL_TYPES.items()
                    ]
                }
            ),
        ),
        patch(
            "custom_components.sa_fuel_pricing.config_flow._fetch_reference_data",
            AsyncMock(return_value=_MOCK_REF),
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "cities"
    # Default for the cities field must include "189"
    schema = result["data_schema"].schema
    cities_field = next(
        k
        for k in schema
        if hasattr(k, "schema") and str(k.schema) == CONF_SELECTED_CITIES
    )
    assert "189" in cities_field.default()


async def test_options_flow_fuel_type_change_creates_entry(hass, config_entry):
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow._api_get",
            AsyncMock(
                return_value={
                    "Fuels": [
                        {"FuelId": k, "Name": v} for k, v in _TEST_FUEL_TYPES.items()
                    ]
                }
            ),
        ),
        patch(
            "custom_components.sa_fuel_pricing.config_flow._fetch_reference_data",
            AsyncMock(return_value=_MOCK_REF),
        ),
    ):
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SELECTED_CITIES: []}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SELECTED_SUBURBS: []}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: []}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_FUEL_TYPES: ["2"], "scan_interval": 10},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_FUEL_TYPES] == [2]
    assert result["data"]["scan_interval"] == 10


async def test_options_flow_api_failure_on_open_aborts(hass, config_entry):
    with patch(
        "custom_components.sa_fuel_pricing.config_flow._api_get",
        AsyncMock(side_effect=aiohttp.ClientError("network error")),
    ):
        result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
