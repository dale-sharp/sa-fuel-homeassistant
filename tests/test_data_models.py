"""Unit tests for SAFuelData, SiteDetail, and SitePrice data models."""
from __future__ import annotations

from datetime import datetime

from custom_components.sa_fuel_pricing.coordinator import SAFuelData, SitePrice


def _price(raw: float, date: str = "2026-06-18T03:31:00") -> SitePrice:
    return SitePrice(
        site_id=1,
        fuel_id=2,
        fuel_name="Unleaded",
        price_raw=raw,
        transaction_date_utc=date,
        collection_method="T",
    )


# --- SitePrice.price_dollars ---

def test_price_normal() -> None:
    assert _price(1579.0).price_dollars == 1.579


def test_price_rounds_to_three_decimals() -> None:
    assert _price(1579.9).price_dollars == 1.580


def test_price_sentinel_returns_none() -> None:
    assert _price(9999.0).price_dollars is None


def test_price_just_below_sentinel_is_valid() -> None:
    assert _price(9998.0).price_dollars == 9.998


def test_price_zero() -> None:
    assert _price(0.0).price_dollars == 0.0


# --- SitePrice.last_updated_local ---

def test_last_updated_valid_utc_string() -> None:
    result = _price(1579.0, "2026-06-18T03:31:00").last_updated_local
    assert isinstance(result, datetime)


def test_last_updated_empty_string() -> None:
    assert _price(1579.0, "").last_updated_local is None


def test_last_updated_malformed_string() -> None:
    assert _price(1579.0, "not-a-date").last_updated_local is None


# --- SAFuelData default factories ---

def test_sadata_instances_do_not_share_mutable_state() -> None:
    a = SAFuelData()
    b = SAFuelData()
    a.sites[99] = object()  # type: ignore[assignment]
    assert 99 not in b.sites
