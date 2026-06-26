"""Config flow for the SA Fuel Pricing integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    ALL_SA_FUEL_IDS,
    API_BASE_URL,
    API_TIMEOUT,
    CONF_FUEL_TYPES,
    CONF_SELECTED_CITIES,
    CONF_SELECTED_SITES,
    CONF_SELECTED_SUBURBS,
    CONF_SUBSCRIBER_TOKEN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    SA_COUNTRY_ID,
    SA_GEO_REGION_ID,
    SA_GEO_REGION_LEVEL,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight data structures used only within the flow
# ---------------------------------------------------------------------------


@dataclass
class _SiteSummary:
    """Minimal site info needed for the selection UI."""

    site_id: int
    name: str
    address: str
    city_region_id: int
    city_name: str
    suburb_region_id: int
    suburb_name: str


@dataclass
class _FlowReferenceData:
    """All reference data fetched once per flow session."""

    fuel_types: dict[int, str]  # fuel_id -> name
    # city_region_id -> city_name  (only cities that have at least one site)
    cities: dict[int, str]
    # suburb_region_id -> (suburb_name, city_region_id)
    suburbs: dict[int, tuple[str, int]]
    # site_id -> _SiteSummary
    sites: dict[int, _SiteSummary]


# ---------------------------------------------------------------------------
# API helpers used during the config flow (before the coordinator exists)
# ---------------------------------------------------------------------------


async def _api_get(
    session: aiohttp.ClientSession,
    token: str,
    path: str,
) -> Any:
    """Perform a single authenticated GET against the SAFPIS API."""
    headers = {
        "Authorization": f"FPDAPI SubscriberToken={token}",
        "Content-Type": "application/json",
    }
    url = f"{API_BASE_URL}{path}"
    async with asyncio.timeout(API_TIMEOUT):
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            return await response.json()


async def _validate_token(hass: HomeAssistant, token: str) -> dict[int, str]:
    """
    Validate token by calling GetCountryFuelTypes.

    Returns fuel_id -> name on success.
    Raises ValueError with an error-key string on failure.
    """
    session = async_get_clientsession(hass)
    try:
        data = await _api_get(
            session,
            token,
            f"/Subscriber/GetCountryFuelTypes?countryId={SA_COUNTRY_ID}",
        )
        return {f["FuelId"]: f["Name"] for f in data.get("Fuels", [])}
    except TimeoutError as err:
        raise ValueError("cannot_connect") from err
    except aiohttp.ClientResponseError as err:
        if err.status == HTTPStatus.UNAUTHORIZED:
            raise ValueError("invalid_auth") from err
        if err.status == HTTPStatus.FORBIDDEN:
            raise ValueError("forbidden") from err
        raise ValueError("cannot_connect") from err
    except aiohttp.ClientError as err:
        raise ValueError("cannot_connect") from err


async def _fetch_reference_data(
    hass: HomeAssistant,
    token: str,
    fuel_types: dict[int, str],
) -> _FlowReferenceData:
    """
    Fetch geo regions and site details for the city/suburb/site selection steps.

    Raises ValueError("cannot_connect") on any network or HTTP error.
    """
    session = async_get_clientsession(hass)
    try:
        geo_data, site_data = await asyncio.gather(
            _api_get(
                session,
                token,
                f"/Subscriber/GetCountryGeographicRegions?countryId={SA_COUNTRY_ID}",
            ),
            _api_get(
                session,
                token,
                f"/Subscriber/GetFullSiteDetails"
                f"?countryId={SA_COUNTRY_ID}"
                f"&geoRegionLevel={SA_GEO_REGION_LEVEL}"
                f"&geoRegionId={SA_GEO_REGION_ID}",
            ),
        )
    except TimeoutError as err:
        raise ValueError("cannot_connect") from err
    except (aiohttp.ClientResponseError, aiohttp.ClientError) as err:
        raise ValueError("cannot_connect") from err

    # Build region lookups: (level, region_id) -> name
    region_name: dict[tuple[int, int], str] = {
        (r["GeoRegionLevel"], r["GeoRegionId"]): r["Name"]
        for r in geo_data.get("GeographicRegions", [])
    }

    # Derive cities and suburbs from actual site data (ground truth)
    cities: dict[int, str] = {}
    suburbs: dict[int, tuple[str, int]] = {}
    sites: dict[int, _SiteSummary] = {}

    for s in site_data.get("S", []):
        site_id = s["S"]
        g1 = s.get("G1", 0)  # suburb region id
        g2 = s.get("G2", 0)  # city region id
        city_name = region_name.get((2, g2), f"Region {g2}")
        suburb_name = region_name.get((1, g1), f"Suburb {g1}")

        cities[g2] = city_name
        suburbs[g1] = (suburb_name, g2)
        sites[site_id] = _SiteSummary(
            site_id=site_id,
            name=s.get("N", "Unknown"),
            address=s.get("A", ""),
            city_region_id=g2,
            city_name=city_name,
            suburb_region_id=g1,
            suburb_name=suburb_name,
        )

    return _FlowReferenceData(
        fuel_types=fuel_types,
        cities=cities,
        suburbs=suburbs,
        sites=sites,
    )


# ---------------------------------------------------------------------------
# Selector builders
# ---------------------------------------------------------------------------


def _city_selector(ref: _FlowReferenceData) -> SelectSelector:
    """Return a multi-select selector for all cities that have active sites."""
    options = [
        SelectOptionDict(value=str(cid), label=name)
        for cid, name in sorted(ref.cities.items(), key=lambda x: x[1])
    ]
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=SelectSelectorMode.LIST,
            custom_value=False,
        )
    )


def _suburb_selector(
    ref: _FlowReferenceData,
    city_ids: set[int],
) -> SelectSelector:
    """Return a selector for suburbs that belong to the selected cities."""
    options = [
        SelectOptionDict(
            value=str(sid),
            label=f"{name}  ({ref.cities.get(city_id, '')})",
        )
        for sid, (name, city_id) in sorted(ref.suburbs.items(), key=lambda x: x[1][0])
        if (not city_ids) or (city_id in city_ids)
    ]
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=SelectSelectorMode.LIST,
            custom_value=False,
        )
    )


def _site_selector(
    ref: _FlowReferenceData,
    suburb_ids: set[int],
    city_ids: set[int],
) -> SelectSelector:
    """Return a selector for sites, filtered to the chosen suburbs or cities."""

    def _site_in_scope(s: _SiteSummary) -> bool:
        if suburb_ids:
            return s.suburb_region_id in suburb_ids
        if city_ids:
            return s.city_region_id in city_ids
        return True  # no filter — show all

    options = [
        SelectOptionDict(
            value=str(s.site_id),
            label=f"{s.name}  —  {s.address}  ({s.suburb_name})",
        )
        for s in sorted(
            ref.sites.values(), key=lambda x: (x.city_name, x.suburb_name, x.name)
        )
        if _site_in_scope(s)
    ]
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=SelectSelectorMode.LIST,
            custom_value=False,
        )
    )


def _fuel_selector(ref: _FlowReferenceData) -> SelectSelector:
    """Return a multi-select selector for available SA fuel types."""
    available_ids = sorted(fid for fid in ref.fuel_types if fid in ALL_SA_FUEL_IDS)
    options = [
        SelectOptionDict(
            value=str(fid),
            label=ref.fuel_types.get(fid, f"Fuel {fid}"),
        )
        for fid in available_ids
    ]
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=SelectSelectorMode.LIST,
            custom_value=False,
        )
    )


def _scan_interval_selector() -> NumberSelector:
    """Return a number selector for the polling interval in minutes."""
    return NumberSelector(
        NumberSelectorConfig(
            min=1,
            max=60,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="minutes",
        )
    )


# ---------------------------------------------------------------------------
# Schema builders (used by both config and options flows)
# ---------------------------------------------------------------------------


def _cities_schema(ref: _FlowReferenceData, default: list[str]) -> vol.Schema:
    """Build the vol.Schema for the cities step."""
    return vol.Schema(
        {vol.Optional(CONF_SELECTED_CITIES, default=default): _city_selector(ref)}
    )


def _suburbs_schema(
    ref: _FlowReferenceData,
    city_ids: set[int],
    default: list[str],
) -> vol.Schema:
    """Build the vol.Schema for the suburbs step."""
    return vol.Schema(
        {
            vol.Optional(CONF_SELECTED_SUBURBS, default=default): _suburb_selector(
                ref, city_ids
            )
        }
    )


def _sites_schema(
    ref: _FlowReferenceData,
    suburb_ids: set[int],
    city_ids: set[int],
    default: list[str],
) -> vol.Schema:
    """Build the vol.Schema for the sites step."""
    return vol.Schema(
        {
            vol.Optional(CONF_SELECTED_SITES, default=default): _site_selector(
                ref, suburb_ids, city_ids
            )
        }
    )


def _fuel_types_schema(
    ref: _FlowReferenceData,
    fuel_default: list[str],
    interval_default: int,
) -> vol.Schema:
    """Build the vol.Schema for the fuel types and polling interval step."""
    return vol.Schema(
        {
            vol.Required(CONF_FUEL_TYPES, default=fuel_default): _fuel_selector(ref),
            vol.Optional(
                CONF_SCAN_INTERVAL, default=interval_default
            ): _scan_interval_selector(),
        }
    )


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------


class SAFuelPricingConfigFlow(ConfigFlow, domain=DOMAIN):
    """
    Multi-step setup flow.

    Steps:
      1. user       — enter subscriber token (validates against API)
      2. cities     — pick one or more SA cities (searchable multi-select)
      3. suburbs    — pick suburbs within chosen cities (filtered, optional)
      4. sites      — pick individual sites within chosen suburbs (filtered, optional)
      5. fuel_types — choose which fuel types to track + poll interval
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._token: str = ""
        self._ref: _FlowReferenceData | None = None
        self._city_ids: list[int] = []
        self._suburb_ids: list[int] = []
        self._site_ids: list[int] = []

    # --- Step 1: Token ---

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step — validate the subscriber token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_SUBSCRIBER_TOKEN].strip()
            try:
                fuel_types = await _validate_token(self.hass, token)
                self._ref = await _fetch_reference_data(self.hass, token, fuel_types)
            except ValueError as err:
                errors["base"] = str(err)
            else:
                self._token = token
                await self.async_set_unique_id(token)
                self._abort_if_unique_id_configured()
                return await self.async_step_cities()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SUBSCRIBER_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
        )

    # --- Step 2: Cities ---

    async def async_step_cities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle city selection."""
        if self._ref is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            self._city_ids = [int(v) for v in user_input.get(CONF_SELECTED_CITIES, [])]
            return await self.async_step_suburbs()
        return self.async_show_form(
            step_id="cities",
            data_schema=_cities_schema(self._ref, default=[]),
            description_placeholders={
                "total_sites": str(len(self._ref.sites)),
                "total_cities": str(len(self._ref.cities)),
            },
            errors={},
        )

    # --- Step 3: Suburbs ---

    async def async_step_suburbs(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle suburb selection."""
        if self._ref is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            self._suburb_ids = [
                int(v) for v in user_input.get(CONF_SELECTED_SUBURBS, [])
            ]
            return await self.async_step_sites()
        return self.async_show_form(
            step_id="suburbs",
            data_schema=_suburbs_schema(self._ref, set(self._city_ids), default=[]),
            description_placeholders={
                "selected_cities": ", ".join(
                    self._ref.cities.get(c, str(c)) for c in self._city_ids
                )
                or "all cities",
            },
        )

    # --- Step 4: Individual sites ---

    async def async_step_sites(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle individual site selection."""
        if self._ref is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            self._site_ids = [int(v) for v in user_input.get(CONF_SELECTED_SITES, [])]
            return await self.async_step_fuel_types()
        return self.async_show_form(
            step_id="sites",
            data_schema=_sites_schema(
                self._ref, set(self._suburb_ids), set(self._city_ids), default=[]
            ),
            description_placeholders={
                "filter_context": _describe_filter(
                    self._ref, self._city_ids, self._suburb_ids
                ),
            },
        )

    # --- Step 5: Fuel types + scan interval ---

    async def async_step_fuel_types(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle fuel type and polling interval selection."""
        if self._ref is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            selected_fuel_ids = [int(v) for v in user_input.get(CONF_FUEL_TYPES, [])]
            scan_interval = int(
                user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
            )
            return self.async_create_entry(
                title="SA Fuel Pricing",
                data={CONF_SUBSCRIBER_TOKEN: self._token},
                options={
                    CONF_SELECTED_CITIES: self._city_ids,
                    CONF_SELECTED_SUBURBS: self._suburb_ids,
                    CONF_SELECTED_SITES: self._site_ids,
                    CONF_FUEL_TYPES: selected_fuel_ids,
                    CONF_SCAN_INTERVAL: scan_interval,
                },
            )
        all_fuel_ids = sorted(
            fid for fid in self._ref.fuel_types if fid in ALL_SA_FUEL_IDS
        )
        return self.async_show_form(
            step_id="fuel_types",
            data_schema=_fuel_types_schema(
                self._ref,
                fuel_default=[str(fid) for fid in all_fuel_ids],
                interval_default=DEFAULT_SCAN_INTERVAL_MINUTES,
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SAFuelPricingOptionsFlow:
        """Return the options flow handler."""
        return SAFuelPricingOptionsFlow(config_entry)

    # --- Reauthentication flow ---

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication triggered by a 401 from the API."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user for a new subscriber token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_SUBSCRIBER_TOKEN].strip()
            try:
                await _validate_token(self.hass, token)
            except ValueError as err:
                errors["base"] = str(err)
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_SUBSCRIBER_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SUBSCRIBER_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
        )

    # --- Reconfiguration flow ---

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """
        Allow the user to replace their subscriber token without removing the entry.

        The new token must belong to the same SAFPIS account.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_SUBSCRIBER_TOKEN].strip()
            try:
                await _validate_token(self.hass, token)
            except ValueError as err:
                errors["base"] = str(err)
            else:
                await self.async_set_unique_id(token)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates={CONF_SUBSCRIBER_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SUBSCRIBER_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Options flow  (same wizard, pre-populated with existing selections)
# ---------------------------------------------------------------------------


class SAFuelPricingOptionsFlow(OptionsFlow):
    """
    Options flow — re-runs the city/suburb/site/fuel wizard with current values.

    Fetches fresh site data from the API when opened.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise with current option values."""
        self._config_entry = config_entry
        self._token: str = config_entry.data[CONF_SUBSCRIBER_TOKEN]
        self._ref: _FlowReferenceData | None = None
        opts = config_entry.options
        self._city_ids: list[int] = list(opts.get(CONF_SELECTED_CITIES, []))
        self._suburb_ids: list[int] = list(opts.get(CONF_SELECTED_SUBURBS, []))
        self._site_ids: list[int] = list(opts.get(CONF_SELECTED_SITES, []))
        self._fuel_ids: list[int] = list(opts.get(CONF_FUEL_TYPES, ALL_SA_FUEL_IDS))
        self._scan_interval: int = opts.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
        )

    async def async_step_init(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """
        Fetch fresh reference data then open city selection.

        Token re-validation is skipped — the token was validated at setup time.
        A 401 from the API here will surface as a cannot_connect abort.
        """
        try:
            session = async_get_clientsession(self.hass)
            fuel_type_data = await _api_get(
                session,
                self._token,
                f"/Subscriber/GetCountryFuelTypes?countryId={SA_COUNTRY_ID}",
            )
            fuel_types = {
                f["FuelId"]: f["Name"] for f in fuel_type_data.get("Fuels", [])
            }
            self._ref = await _fetch_reference_data(self.hass, self._token, fuel_types)
        except (ValueError, TimeoutError, aiohttp.ClientError):
            _LOGGER.exception("Failed to fetch SAFPIS reference data in options flow")
            return self.async_abort(reason="cannot_connect")

        return await self.async_step_cities()

    async def async_step_cities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle city selection step."""
        if self._ref is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            self._city_ids = [int(v) for v in user_input.get(CONF_SELECTED_CITIES, [])]
            return await self.async_step_suburbs()
        return self.async_show_form(
            step_id="cities",
            data_schema=_cities_schema(
                self._ref, default=[str(c) for c in self._city_ids]
            ),
            description_placeholders={
                "total_sites": str(len(self._ref.sites)),
                "total_cities": str(len(self._ref.cities)),
            },
        )

    async def async_step_suburbs(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle suburb selection step."""
        if self._ref is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            self._suburb_ids = [
                int(v) for v in user_input.get(CONF_SELECTED_SUBURBS, [])
            ]
            return await self.async_step_sites()
        return self.async_show_form(
            step_id="suburbs",
            data_schema=_suburbs_schema(
                self._ref,
                set(self._city_ids),
                default=[str(s) for s in self._suburb_ids],
            ),
            description_placeholders={
                "selected_cities": ", ".join(
                    self._ref.cities.get(c, str(c)) for c in self._city_ids
                )
                or "all cities",
            },
        )

    async def async_step_sites(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle individual site selection step."""
        if self._ref is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            self._site_ids = [int(v) for v in user_input.get(CONF_SELECTED_SITES, [])]
            return await self.async_step_fuel_types()
        return self.async_show_form(
            step_id="sites",
            data_schema=_sites_schema(
                self._ref,
                set(self._suburb_ids),
                set(self._city_ids),
                default=[str(s) for s in self._site_ids],
            ),
            description_placeholders={
                "filter_context": _describe_filter(
                    self._ref, self._city_ids, self._suburb_ids
                ),
            },
        )

    async def async_step_fuel_types(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle fuel type and polling interval selection step."""
        if self._ref is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            selected_fuel_ids = [int(v) for v in user_input.get(CONF_FUEL_TYPES, [])]
            scan_interval = int(
                user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_SELECTED_CITIES: self._city_ids,
                    CONF_SELECTED_SUBURBS: self._suburb_ids,
                    CONF_SELECTED_SITES: self._site_ids,
                    CONF_FUEL_TYPES: selected_fuel_ids,
                    CONF_SCAN_INTERVAL: scan_interval,
                },
            )
        all_fuel_ids = sorted(
            fid for fid in self._ref.fuel_types if fid in ALL_SA_FUEL_IDS
        )
        current_default = (
            [str(f) for f in self._fuel_ids]
            if self._fuel_ids
            else [str(f) for f in all_fuel_ids]
        )
        return self.async_show_form(
            step_id="fuel_types",
            data_schema=_fuel_types_schema(
                self._ref,
                fuel_default=current_default,
                interval_default=self._scan_interval,
            ),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _describe_filter(
    ref: _FlowReferenceData,
    city_ids: list[int],
    suburb_ids: list[int],
) -> str:
    """Return a human-readable description of the active city/suburb filter."""
    if suburb_ids:
        names = [ref.suburbs.get(s, (str(s), 0))[0] for s in suburb_ids]
        return "suburbs: " + ", ".join(sorted(names))
    if city_ids:
        names = [ref.cities.get(c, str(c)) for c in city_ids]
        return "cities: " + ", ".join(sorted(names))
    return "all of South Australia"
