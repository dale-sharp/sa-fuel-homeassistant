"""Diagnostics support for SA Fuel Pricing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_SUBSCRIBER_TOKEN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import SAFuelConfigEntry
    from .coordinator import SAFuelData, SAFuelDataCoordinator

# Fields that must never appear in diagnostics output.
_TO_REDACT = {CONF_SUBSCRIBER_TOKEN}


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant,
    entry: SAFuelConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: SAFuelDataCoordinator = entry.runtime_data
    data: SAFuelData | None = coordinator.data

    site_summary: list[dict[str, Any]] = []
    price_summary: list[dict[str, Any]] = []

    if data is not None:
        site_summary.extend(
            {
                "site_id": site.site_id,
                "name": site.name,
                "address": site.address,
                "postcode": site.postcode,
                "brand": site.brand_name,
                "suburb": site.suburb,
                "city": site.city,
                # Coordinates omitted - personally identifiable / sensitive
            }
            for site in list(data.sites.values())[:10]
        )
        price_summary.extend(
            {
                "site_id": site_id,
                "site_name": site_name.name if site_name else "unknown",
                "prices": {
                    data.fuel_types.get(fid, str(fid)): p.price_dollars
                    for fid, p in fuel_prices.items()
                },
            }
            for site_id, fuel_prices in list(data.prices.items())[:10]
            if (site_name := data.sites.get(site_id)) or True
        )

    return {
        "entry_data": async_redact_data(dict(entry.data), _TO_REDACT),
        "options": dict(entry.options),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            "update_interval_seconds": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
        },
        "data_summary": {
            "total_sites": len(data.sites) if data else 0,
            "tracked_sites": len(data.prices) if data else 0,
            "total_price_entries": sum(len(v) for v in data.prices.values())
            if data
            else 0,
            "fuel_types": data.fuel_types if data else {},
            "sample_sites": site_summary,
            "sample_prices": price_summary,
        },
    }
