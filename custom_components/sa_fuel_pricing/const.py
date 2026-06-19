"""Constants for the SA Fuel Pricing integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "sa_fuel_pricing"

# Configuration keys
CONF_SUBSCRIBER_TOKEN = "subscriber_token"  # noqa: S105
CONF_FUEL_TYPES = "fuel_types"
# CONF_SCAN_INTERVAL is imported from homeassistant.const — do not redefine here

# Site selection options — stored in entry.options
# Each is a list of integer IDs; empty list = "all" for that level
CONF_SELECTED_CITIES = "selected_cities"  # list[int]  G2 region IDs
CONF_SELECTED_SUBURBS = "selected_suburbs"  # list[int]  G1 region IDs
CONF_SELECTED_SITES = "selected_sites"  # list[int]  site IDs

# Defaults
DEFAULT_SCAN_INTERVAL_MINUTES = 5
DEFAULT_SCAN_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)
REFERENCE_DATA_UPDATE_INTERVAL = timedelta(hours=24)

# API
API_BASE_URL = "https://fppdirectapi-prod.safuelpricinginformation.com.au"
API_TIMEOUT = 30

# SA geographic constants
SA_COUNTRY_ID = 21
SA_GEO_REGION_LEVEL = 3
SA_GEO_REGION_ID = 4  # South Australia

# Price sentinel: means fuel type unavailable at this site
PRICE_UNAVAILABLE = 9999
# API prices are in tenths-of-a-cent (e.g. 1579 = $1.579/L).
# Divide by 1000 to convert to dollars per litre.
PRICE_DIVISOR = 1000.0

# Fuel type IDs known to appear in SA price data
FUEL_TYPE_UNLEADED = 2
FUEL_TYPE_DIESEL = 3
FUEL_TYPE_LPG = 4
FUEL_TYPE_PREMIUM_95 = 5
FUEL_TYPE_PREMIUM_98 = 8
FUEL_TYPE_E10 = 12
FUEL_TYPE_PREMIUM_DIESEL = 14
FUEL_TYPE_E85 = 19

# All fuel IDs that can appear in SA price data (used as option defaults)
ALL_SA_FUEL_IDS: list[int] = [
    FUEL_TYPE_UNLEADED,
    FUEL_TYPE_DIESEL,
    FUEL_TYPE_LPG,
    FUEL_TYPE_PREMIUM_95,
    FUEL_TYPE_PREMIUM_98,
    FUEL_TYPE_E10,
    FUEL_TYPE_PREMIUM_DIESEL,
    FUEL_TYPE_E85,
]

# Less common fuel types disabled by default to reduce entity noise.
# Users who need them can enable them individually in the entity registry.
FUEL_IDS_DISABLED_BY_DEFAULT: frozenset[int] = frozenset(
    {
        FUEL_TYPE_LPG,  # LPG — not universally available
        FUEL_TYPE_E85,  # E85 — very few sites stock it
    }
)

# Unit
UNIT_DOLLARS_PER_LITRE = "AUD/L"
