"""Tests for SAFuelEntity."""

from __future__ import annotations

from custom_components.sa_fuel_pricing.entity import SAFuelEntity

from .conftest import SITE_A, TEST_DATA


def test_current_site_falls_back_to_cached_site_when_coordinator_data_is_none(
    coordinator,
):
    coordinator.data = None
    entity = SAFuelEntity(coordinator, SITE_A)

    assert entity.current_site is SITE_A


def test_current_site_returns_fresh_site_from_coordinator_data(coordinator):
    coordinator.data = TEST_DATA
    entity = SAFuelEntity(coordinator, SITE_A)

    assert entity.current_site is TEST_DATA.sites[SITE_A.site_id]
