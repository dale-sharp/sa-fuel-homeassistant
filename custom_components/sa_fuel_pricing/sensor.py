"""Sensor platform for the SA Fuel Pricing integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass

from .const import (
    FUEL_IDS_DISABLED_BY_DEFAULT,
    FUEL_TYPE_DIESEL,
    FUEL_TYPE_E10,
    FUEL_TYPE_E85,
    FUEL_TYPE_LPG,
    FUEL_TYPE_PREMIUM_95,
    FUEL_TYPE_PREMIUM_98,
    FUEL_TYPE_PREMIUM_DIESEL,
    FUEL_TYPE_UNLEADED,
    UNIT_DOLLARS_PER_LITRE,
)
from .entity import SAFuelEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import SAFuelConfigEntry
    from .coordinator import SAFuelDataCoordinator, SiteDetail, SitePrice

_LOGGER = logging.getLogger(__name__)

# Coordinator centralises all data fetching; no per-entity polling needed.
PARALLEL_UPDATES = 0

# Maps fuel_id -> translation_key for entity naming.
# Fuel types not listed here fall back to a generic name via _attr_name.
_FUEL_TRANSLATION_KEYS: dict[int, str] = {
    FUEL_TYPE_UNLEADED: "unleaded",
    FUEL_TYPE_DIESEL: "diesel",
    FUEL_TYPE_LPG: "lpg",
    FUEL_TYPE_PREMIUM_95: "premium_95",
    FUEL_TYPE_PREMIUM_98: "premium_98",
    FUEL_TYPE_E10: "e10",
    FUEL_TYPE_PREMIUM_DIESEL: "premium_diesel",
    FUEL_TYPE_E85: "e85",
}


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SAFuelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SA Fuel Pricing sensor entities from a config entry."""
    coordinator: SAFuelDataCoordinator = entry.runtime_data

    def _add_new_entities() -> None:
        """Create entities for any (site_id, fuel_id) pairs not yet tracked."""
        if coordinator.data is None:
            return

        new_entities: list[SAFuelSensor] = []
        for site_id, fuel_prices in coordinator.data.prices.items():
            site = coordinator.data.sites.get(site_id)
            if site is None:
                _LOGGER.debug("Skipping site_id %s: no site details found", site_id)
                continue
            for fuel_id in fuel_prices:
                key = (site_id, fuel_id)
                if key not in coordinator.tracked_entity_keys:
                    coordinator.tracked_entity_keys.add(key)
                    new_entities.append(SAFuelSensor(coordinator, site, fuel_id))

        if new_entities:
            _LOGGER.debug(
                "Adding %d new SA Fuel Pricing sensor entities", len(new_entities)
            )
            async_add_entities(new_entities)

    # Initial population
    _add_new_entities()

    # Re-check on every coordinator update to pick up newly appearing sites
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class SAFuelSensor(SAFuelEntity, SensorEntity):
    """A sensor representing the price of one fuel type at one SA fuel station."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UNIT_DOLLARS_PER_LITRE
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: SAFuelDataCoordinator,
        site: SiteDetail,
        fuel_id: int,
    ) -> None:
        """Initialise the sensor for a specific fuel type at a specific site."""
        super().__init__(coordinator, site)
        self._fuel_id = fuel_id

        self._attr_unique_id = f"sa_fuel_{site.site_id}_{fuel_id}"
        # Use a translation key for known fuel types so the entity name is
        # translatable. Fall back to a plain name for any unknown fuel ID.
        translation_key = _FUEL_TRANSLATION_KEYS.get(fuel_id)
        if translation_key is not None:
            self._attr_translation_key = translation_key
        else:
            self._attr_name = (
                coordinator.data.fuel_types.get(fuel_id, f"Fuel {fuel_id}")
                if coordinator.data
                else f"Fuel {fuel_id}"
            )
        # Disable uncommon fuel types by default to reduce entity noise.
        if fuel_id in FUEL_IDS_DISABLED_BY_DEFAULT:
            self._attr_entity_registry_enabled_default = False

    @property
    def _current_price(self) -> SitePrice | None:
        """Return the current SitePrice for this sensor, or None."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.prices.get(self._site_id, {}).get(self._fuel_id)

    @property
    def native_value(self) -> float | None:
        """Return the fuel price in AUD/L, or None if unavailable."""
        price = self._current_price
        if price is None:
            return None
        return price.price_dollars

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional sensor attributes."""
        site = self.current_site
        price = self._current_price
        attrs: dict[str, Any] = {
            "site_id": site.site_id,
            "site_name": site.name,
            "site_address": site.address,
            "postcode": site.postcode,
            "brand": site.brand_name,
            "suburb": site.suburb,
            "city": site.city,
        }
        if site.latitude is not None:
            attrs["latitude"] = site.latitude
        if site.longitude is not None:
            attrs["longitude"] = site.longitude

        if price is not None:
            attrs["fuel_id"] = price.fuel_id
            attrs["fuel_type"] = price.fuel_name
            attrs["collection_method"] = price.collection_method
            last_updated = price.last_updated_local
            if last_updated is not None:
                attrs["last_updated"] = last_updated
            attrs["unavailable"] = price.price_dollars is None

        return attrs
