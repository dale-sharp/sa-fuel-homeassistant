# Copyright (c) 2026 dale-sharp

"""Tests for SAFuelPricingConfigFlow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from custom_components.sa_fuel_pricing.config_flow import (
    SAFuelPricingConfigFlow,
    _describe_filter,
    _fetch_reference_data,
    _FlowReferenceData,
    _SiteSummary,
    _validate_token,
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

_DUMMY_REQUEST_INFO = aiohttp.RequestInfo(
    url=URL("http://example.com"),
    method="GET",
    headers=CIMultiDictProxy(CIMultiDict()),
)


def _make_timeout_session() -> MagicMock:
    """A mock aiohttp session whose request raises TimeoutError."""
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(side_effect=TimeoutError)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_cm)
    return mock_session


def _make_status_error_session(status: int) -> MagicMock:
    """A mock aiohttp session whose response raises a ClientResponseError."""
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=aiohttp.ClientResponseError(_DUMMY_REQUEST_INFO, (), status=status)
    )
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_cm)
    return mock_session


def _make_json_session(json_data: dict) -> MagicMock:
    """A mock aiohttp session whose response returns the given JSON."""
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=json_data)
    mock_response.raise_for_status = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_cm)
    return mock_session


def _make_client_error_session() -> MagicMock:
    """A mock aiohttp session whose request raises a generic ClientError."""
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("boom"))
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_cm)
    return mock_session


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


async def test_duplicate_token_different_case_aborts(hass):
    await _run_full_flow(hass)  # first setup, uses _TEST_TOKEN

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
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: _TEST_TOKEN.lower()}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_no_cities_selected_entry_has_empty_lists(hass):
    result = await _run_full_flow(hass)

    assert result["options"][CONF_SELECTED_CITIES] == []
    assert result["options"][CONF_SELECTED_SUBURBS] == []
    assert result["options"][CONF_SELECTED_SITES] == []


async def test_suburb_filter_selected_creates_entry(hass):
    # Selecting a suburb exercises the sites step's suburb-scoped selector when its
    # form is generated (as opposed to city-scoped or unfiltered).
    result = await _run_full_flow(hass, suburbs=[170227225], fuel_types=[2])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SELECTED_SUBURBS] == [170227225]


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


async def test_reconfigure_same_account_different_case_updates_entry(hass):
    """Reconfigure with the same token in different casing still matches the account."""
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
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: _TEST_TOKEN.lower()}
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


# --- _validate_token / _fetch_reference_data error mapping ---


async def test_validate_token_timeout_raises_cannot_connect(hass):
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow.async_get_clientsession",
            return_value=_make_timeout_session(),
        ),
        pytest.raises(ValueError, match="cannot_connect"),
    ):
        await _validate_token(hass, _TEST_TOKEN)


async def test_validate_token_forbidden_raises_forbidden(hass):
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow.async_get_clientsession",
            return_value=_make_status_error_session(403),
        ),
        pytest.raises(ValueError, match="forbidden"),
    ):
        await _validate_token(hass, _TEST_TOKEN)


async def test_validate_token_unauthorized_raises_invalid_auth(hass):
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow.async_get_clientsession",
            return_value=_make_status_error_session(401),
        ),
        pytest.raises(ValueError, match="invalid_auth"),
    ):
        await _validate_token(hass, _TEST_TOKEN)


async def test_validate_token_other_http_error_raises_cannot_connect(hass):
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow.async_get_clientsession",
            return_value=_make_status_error_session(500),
        ),
        pytest.raises(ValueError, match="cannot_connect"),
    ):
        await _validate_token(hass, _TEST_TOKEN)


async def test_validate_token_success_returns_fuel_types(hass):
    with patch(
        "custom_components.sa_fuel_pricing.config_flow.async_get_clientsession",
        return_value=_make_json_session(
            {"Fuels": [{"FuelId": k, "Name": v} for k, v in _TEST_FUEL_TYPES.items()]}
        ),
    ):
        result = await _validate_token(hass, _TEST_TOKEN)

    assert result == _TEST_FUEL_TYPES


async def test_validate_token_client_error_raises_cannot_connect(hass):
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow.async_get_clientsession",
            return_value=_make_client_error_session(),
        ),
        pytest.raises(ValueError, match="cannot_connect"),
    ):
        await _validate_token(hass, _TEST_TOKEN)


async def test_fetch_reference_data_timeout_raises_cannot_connect(hass):
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow.async_get_clientsession",
            return_value=_make_timeout_session(),
        ),
        pytest.raises(ValueError, match="cannot_connect"),
    ):
        await _fetch_reference_data(hass, _TEST_TOKEN, _TEST_FUEL_TYPES)


async def test_fetch_reference_data_client_error_raises_cannot_connect(hass):
    with (
        patch(
            "custom_components.sa_fuel_pricing.config_flow.async_get_clientsession",
            return_value=_make_client_error_session(),
        ),
        pytest.raises(ValueError, match="cannot_connect"),
    ):
        await _fetch_reference_data(hass, _TEST_TOKEN, _TEST_FUEL_TYPES)


async def test_fetch_reference_data_success_returns_reference_data(hass):
    # Both concurrent _api_get calls (geo regions, site details) hit the same mocked
    # session, so one combined payload with both response shapes' keys serves both.
    combined_json = {
        "GeographicRegions": [
            {"GeoRegionLevel": 2, "GeoRegionId": 189, "Name": "Adelaide"},
            {"GeoRegionLevel": 1, "GeoRegionId": 170227225, "Name": "Dry Creek"},
        ],
        "S": [
            {
                "S": 61205460,
                "N": "OTR Dry Creek",
                "A": "17 Vater St",
                "G1": 170227225,
                "G2": 189,
            },
        ],
    }
    with patch(
        "custom_components.sa_fuel_pricing.config_flow.async_get_clientsession",
        return_value=_make_json_session(combined_json),
    ):
        result = await _fetch_reference_data(hass, _TEST_TOKEN, _TEST_FUEL_TYPES)

    assert result.fuel_types == _TEST_FUEL_TYPES
    assert result.cities == {189: "Adelaide"}
    assert result.suburbs == {170227225: ("Dry Creek", 189)}
    assert result.sites[61205460].name == "OTR Dry Creek"
    assert result.sites[61205460].city_region_id == 189


# --- Defensive _ref-is-None guards ---


async def test_cities_step_aborts_when_ref_not_set():
    flow = SAFuelPricingConfigFlow()
    result = await flow.async_step_cities()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown"


async def test_suburbs_step_aborts_when_ref_not_set():
    flow = SAFuelPricingConfigFlow()
    result = await flow.async_step_suburbs()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown"


async def test_sites_step_aborts_when_ref_not_set():
    flow = SAFuelPricingConfigFlow()
    result = await flow.async_step_sites()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown"


async def test_fuel_types_step_aborts_when_ref_not_set():
    flow = SAFuelPricingConfigFlow()
    result = await flow.async_step_fuel_types()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown"


# --- Reconfigure: invalid token ---


async def test_reconfigure_invalid_token_shows_error(hass):
    await _run_full_flow(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch(
        "custom_components.sa_fuel_pricing.config_flow._validate_token",
        AsyncMock(side_effect=ValueError("invalid_auth")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SUBSCRIBER_TOKEN: "bad-token"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"]["base"] == "invalid_auth"


# --- _describe_filter ---


def test_describe_filter_with_suburbs():
    result = _describe_filter(_MOCK_REF, city_ids=[189, 190], suburb_ids=[170227225])
    assert result == "suburbs: Dry Creek"
