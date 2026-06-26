"""Tests for SAFuelSensor."""

from __future__ import annotations

from custom_components.sa_fuel_pricing.const import FUEL_IDS_DISABLED_BY_DEFAULT
from custom_components.sa_fuel_pricing.coordinator import SAFuelData
from custom_components.sa_fuel_pricing.sensor import SAFuelSensor

from .conftest import (
    PRICE_A_ULP,
    SITE_A,
    SITE_C,
    TEST_DATA,
)


def _sensor(coordinator, site=SITE_A, fuel_id=2) -> SAFuelSensor:
    """Construct a SAFuelSensor without going through HA entity platform setup."""
    return SAFuelSensor(coordinator, site, fuel_id)


# --- native_value ---


def test_native_value_returns_correct_price(coordinator):
    coordinator.data = TEST_DATA
    sensor = _sensor(coordinator, SITE_A, fuel_id=2)
    assert sensor.native_value == 1.579


def test_native_value_returns_none_for_sentinel_price(coordinator):
    coordinator.data = TEST_DATA
    sensor = _sensor(coordinator, SITE_A, fuel_id=3)  # Diesel is 9999
    assert sensor.native_value is None


def test_native_value_returns_none_when_coordinator_data_is_none(coordinator):
    coordinator.data = None
    sensor = _sensor(coordinator, SITE_A, fuel_id=2)
    assert sensor.native_value is None


# --- extra_state_attributes ---


def test_extra_state_attributes_contains_expected_keys(coordinator):
    coordinator.data = TEST_DATA
    sensor = _sensor(coordinator, SITE_A, fuel_id=2)
    attrs = sensor.extra_state_attributes

    for key in (
        "site_id",
        "site_name",
        "brand",
        "suburb",
        "city",
        "fuel_type",
        "collection_method",
    ):
        assert key in attrs, f"Missing key: {key}"


def test_extra_state_attributes_includes_coordinates_when_present(coordinator):
    coordinator.data = TEST_DATA
    sensor = _sensor(coordinator, SITE_A, fuel_id=2)
    attrs = sensor.extra_state_attributes

    assert "latitude" in attrs
    assert "longitude" in attrs


def test_extra_state_attributes_omits_coordinates_when_null(coordinator):
    coordinator.data = TEST_DATA
    sensor = _sensor(coordinator, SITE_C, fuel_id=12)  # Site C has null lat/lng
    attrs = sensor.extra_state_attributes

    assert "latitude" not in attrs
    assert "longitude" not in attrs


# --- Entity naming ---


def test_known_fuel_type_uses_translation_key(coordinator):
    coordinator.data = TEST_DATA
    sensor = _sensor(coordinator, SITE_A, fuel_id=2)  # ULP — known

    assert sensor._attr_translation_key == "unleaded"
    assert not hasattr(sensor, "_attr_name") or sensor._attr_name is None


def test_unknown_fuel_type_falls_back_to_name(coordinator):
    # Use fuel_id 99 which is not in _FUEL_TRANSLATION_KEYS
    coordinator.data = SAFuelData(
        sites=TEST_DATA.sites,
        prices={SITE_A.site_id: {99: PRICE_A_ULP}},
        brands=TEST_DATA.brands,
        fuel_types={99: "Mystery Fuel"},
        geo_regions=TEST_DATA.geo_regions,
    )
    sensor = _sensor(coordinator, SITE_A, fuel_id=99)

    assert sensor._attr_name == "Mystery Fuel"


# --- Disabled by default ---


def test_disabled_by_default_fuel_types(coordinator):
    coordinator.data = TEST_DATA
    for fuel_id in FUEL_IDS_DISABLED_BY_DEFAULT:
        sensor = _sensor(coordinator, SITE_A, fuel_id=fuel_id)
        assert sensor._attr_entity_registry_enabled_default is False


def test_standard_fuel_types_are_enabled_by_default(coordinator):
    coordinator.data = TEST_DATA
    sensor = _sensor(coordinator, SITE_A, fuel_id=2)
    # _attr_entity_registry_enabled_default defaults to True when not overridden
    assert getattr(sensor, "_attr_entity_registry_enabled_default", True) is True
