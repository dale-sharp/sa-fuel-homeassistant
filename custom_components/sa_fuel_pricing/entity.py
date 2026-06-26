"""Base entity for the SA Fuel Pricing integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_IDENTIFIER_PREFIX, DOMAIN
from .coordinator import SAFuelDataCoordinator, SiteDetail


class SAFuelEntity(CoordinatorEntity[SAFuelDataCoordinator]):
    """
    Base entity for all SA Fuel Pricing entities.

    Holds the coordinator wiring, device registration, and site-data helpers
    common to every entity type this integration may add in future.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SAFuelDataCoordinator,
        site: SiteDetail,
    ) -> None:
        """Initialise the base entity with coordinator and site snapshot."""
        super().__init__(coordinator)
        self._site_id = site.site_id
        # Cache the site snapshot used at construction time; coordinator data
        # may not yet be populated when __init__ runs (e.g. after a restore).
        self._site = site

        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, f"{DEVICE_IDENTIFIER_PREFIX}{site.site_id}")},
            name=site.name,
            manufacturer=site.brand_name,
            model=site.address,
            suggested_area=site.suburb or site.city or None,
        )

    @property
    def current_site(self) -> SiteDetail:
        """Return the freshest available SiteDetail for this entity's site."""
        if self.coordinator.data is None:
            return self._site
        return self.coordinator.data.sites.get(self._site_id, self._site)
