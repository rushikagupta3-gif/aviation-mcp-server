"""Reliability + safety tests for the airspace compute layer.

These verify the deterministic guards an LLM CANNOT bypass: no-fly zones
block routes, altitude limits are enforced, and edge cases are handled.
"""
import pytest

from src.data_layer import AirspaceDB, haversine_km
from src.compute import query_constraints, plan_route

db = AirspaceDB()

# Known points from the dataset
OPEN_MARINA = (1.2806, 103.8636)      # open, 60m
CHANGI = (1.3644, 103.9915)           # controlled, no-fly
JURONG = (1.2667, 103.7000)           # restricted, no-fly


def test_haversine_zero_distance():
    assert haversine_km(OPEN_MARINA, OPEN_MARINA) == pytest.approx(0.0, abs=1e-6)


def test_open_area_allows_flight():
    c = query_constraints(db, OPEN_MARINA)
    assert c["permission_required"] is False
    assert c["max_altitude_m"] == 60


def test_controlled_zone_requires_permission():
    c = query_constraints(db, CHANGI)
    assert c["permission_required"] is True
    assert c["max_altitude_m"] == 0


def test_restricted_zone_is_no_fly():
    c = query_constraints(db, JURONG)
    assert c["max_altitude_m"] == 0
    assert "MINDEF" in c["permission_authorities"]


# ---- SAFETY: routes through no-fly zones must be blocked ---- #
def test_route_through_changi_blocked():
    # A leg that passes near Changi should be flagged infeasible
    route = plan_route(db, [OPEN_MARINA, CHANGI], altitude_m=50)
    assert route.feasible is False
    assert len(route.violations) >= 1


def test_route_in_open_area_feasible():
    nearby = (1.2810, 103.8640)
    route = plan_route(db, [OPEN_MARINA, nearby], altitude_m=50)
    assert route.feasible is True
    assert route.violations == []


def test_altitude_over_open_limit_blocked():
    nearby = (1.2810, 103.8640)
    route = plan_route(db, [OPEN_MARINA, nearby], altitude_m=120)
    assert route.feasible is False


def test_single_waypoint_rejected():
    with pytest.raises(ValueError):
        plan_route(db, [OPEN_MARINA], altitude_m=50)


def test_route_total_distance_positive():
    route = plan_route(db, [OPEN_MARINA, (1.30, 103.87)], altitude_m=40)
    assert route.total_distance_km > 0
