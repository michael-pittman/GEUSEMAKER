from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from geusemaker.models.compute import InstanceSelection, SavingsComparison
from geusemaker.services.compute.selector import InstanceTypeSelector


class FakeSpotService:
    def __init__(self, selections, scores):
        self.selections = selections
        self.scores = scores

    def select_instance_type(self, config):
        return self.selections[config.instance_type]

    def analyze_spot_prices(self, instance_type, region):
        item = self.selections[instance_type]
        return SimpleNamespace(placement_scores_by_az={item.availability_zone: self.scores[instance_type]})


def selection(instance_type: str, price: str, *, spot: bool = True) -> InstanceSelection:
    return InstanceSelection(
        instance_type=instance_type,
        availability_zone="us-east-1a",
        is_spot=spot,
        price_per_hour=Decimal(price),
        selection_reason="test",
        savings_vs_on_demand=SavingsComparison(
            on_demand_hourly=Decimal(price) * 2,
            selected_hourly=Decimal(price),
            hourly_savings=Decimal(price),
            monthly_savings=Decimal(price) * 730,
            savings_percentage=50.0 if spot else 0.0,
        ),
    )


@pytest.fixture
def selector(monkeypatch):
    monkeypatch.setattr(InstanceTypeSelector, "CPU_INSTANCE_TYPES", ["slow", "cheap", "available"])
    result = InstanceTypeSelector.__new__(InstanceTypeSelector)
    result._region = "us-east-1"
    result._spot_service = FakeSpotService(
        {
            "slow": selection("slow", "0.30"),
            "cheap": selection("cheap", "0.10"),
            "available": selection("available", "0.20"),
        },
        {"slow": 2.0, "cheap": 1.0, "available": 9.0},
    )
    return result


def test_lowest_cost_evaluates_all_candidates(selector):
    result = selector.select_best_instance("cpu", preference="lowest_cost")
    assert result.instance_type == "cheap"
    assert [item.instance_type for item in result.alternatives] == ["available", "slow"]


def test_highest_availability_uses_capacity_score(selector):
    assert selector.select_best_instance("cpu", preference="highest_availability").instance_type == "available"


def test_performance_uses_highest_capability_candidate(selector):
    assert selector.select_best_instance("cpu", preference="performance").instance_type == "available"


def test_on_demand_fallback_is_reported(selector):
    for name, price in (("cheap", "0.01"), ("slow", "0.02"), ("available", "0.03")):
        selector._spot_service.selections[name] = selection(name, price, spot=False)
    result = selector.select_best_instance("cpu", preference="lowest_cost", use_spot=True)
    assert result.instance_type == "cheap"
    assert result.fallback_occurred is True
