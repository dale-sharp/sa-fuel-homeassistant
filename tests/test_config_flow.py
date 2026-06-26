"""Tests for SAFuelPricingConfigFlow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.sa_fuel_pricing.config_flow import (
    _FlowReferenceData,
    _SiteSummary,
)
from custom_components.sa_fuel_pricing.const import (
    CONF_FUEL_TYPES,
    CONF_SELECTED_CITIES,
    CONF_SELECTED_SITES,
    CONF_SELECTED_SUBURBS,
    CONF_SUBSCRIBER_TOKEN,
    DOMAIN,
)

# Allow HA's loader to discover custom_components/sa_fuel_pricing during tests.
pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

_TEST_TOKEN = "2FEB37D3-0000-0000-0000-000000000001"  # noqa: S105
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
        61501012: _SiteSummary(
            61501012,
            "OTR Nuriootpa",
            "5 Research Rd",
            190,
            "Barossa",
            170227300,
            "Nuriootpa",
        ),
    },
)


async def _run_full_flow(  # noqa: PLR0913
    hass, *, token=_TEST_TOKEN, cities=None, suburbs=None, sites=None, fuel_types=None
):
    """Walk through all 5 steps with the given selections. Returns the final FlowResult."""
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow._validate_token",
            AsyncMock(return_value=_TEST_FUEL_TYPES),
        ),
        patch(
            "custom_components.sa_fuel_pricing.config_flow._fetch_reference_data",
            AsyncMock(return_value=_MOCK_REF),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: token}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_CITIES: [str(c) for c in (cities or [])]}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_SUBURBS: [str(s) for s in (suburbs or [])]},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: [str(s) for s in (sites or [])]}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_FUEL_TYPES: [
                    str(fid) for fid in (fuel_types or list(_TEST_FUEL_TYPES))
                ],
                "scan_interval": 5,
            },
        )


async def test_happy_path_creates_entry(hass):
    result = await _run_full_flow(hass, cities=[189], fuel_types=[2, 3])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SUBSCRIBER_TOKEN] == _TEST_TOKEN
    assert result["options"][CONF_SELECTED_CITIES] == [189]
    assert result["options"][CONF_FUEL_TYPES] == [2, 3]


async def test_invalid_token_shows_error(hass):
    with patch(
        "custom_components.sa_fuel_pricing.config_flow._validate_token",
        AsyncMock(side_effect=ValueError("invalid_auth")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: "bad-token"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "invalid_auth"


async def test_timeout_shows_cannot_connect_error(hass):
    with patch(
        "custom_components.sa_fuel_pricing.config_flow._validate_token",
        AsyncMock(side_effect=ValueError("cannot_connect")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: _TEST_TOKEN}
        )

    assert result["errors"]["base"] == "cannot_connect"
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_duplicate_token_aborts(hass):
    await _run_full_flow(hass)  # first setup

    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow._validate_token",
            AsyncMock(return_value=_TEST_FUEL_TYPES),
        ),
        patch(
            "custom_components.sa_fuel_pricing.config_flow._fetch_reference_data",
            AsyncMock(return_value=_MOCK_REF),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: _TEST_TOKEN}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_no_cities_selected_entry_has_empty_lists(hass):
    result = await _run_full_flow(hass)

    assert result["options"][CONF_SELECTED_CITIES] == []
    assert result["options"][CONF_SELECTED_SUBURBS] == []
    assert result["options"][CONF_SELECTED_SITES] == []


async def test_reauth_valid_token_updates_entry(hass):
    await _run_full_flow(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch(
        "custom_components.sa_fuel_pricing.config_flow._validate_token",
        AsyncMock(return_value=_TEST_FUEL_TYPES),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: _TEST_TOKEN}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_invalid_token_shows_error(hass):
    await _run_full_flow(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch(
        "custom_components.sa_fuel_pricing.config_flow._validate_token",
        AsyncMock(side_effect=ValueError("invalid_auth")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: "bad"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_reconfigure_same_account_updates_entry(hass):
    """Reconfigure with the same token (same unique_id) succeeds."""
    await _run_full_flow(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch(
        "custom_components.sa_fuel_pricing.config_flow._validate_token",
        AsyncMock(return_value=_TEST_FUEL_TYPES),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: _TEST_TOKEN}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_different_account_aborts(hass):
    await _run_full_flow(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    other_token = "AAAAAAAA-0000-0000-0000-000000000099"  # noqa: S105

    with patch(
        "custom_components.sa_fuel_pricing.config_flow._validate_token",
        AsyncMock(return_value=_TEST_FUEL_TYPES),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: other_token}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
