"""Computation + query layer  —  PERSON E (Rushika) owns this module.

Two responsibilities, both surfaced to the LLM as callable MCP tools:

  1. query_constraints(point)   -> what rules apply at a location
  2. plan_route(waypoints, alt) -> feasibility calc across a flight path

These are pure, deterministic functions so the LLM's tool calls are
auditable and testable (the safety suite, Person F, depends on that).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from .data_layer import AirspaceDB, Zone, haversine_km

Point = tuple[float, float]


# --------------------------------------------------------------------------- #
# Query layer
# --------------------------------------------------------------------------- #
def query_constraints(db: AirspaceDB, point: Point,
                      when: Optional[datetime] = None) -> dict:
    """Return all airspace constraints that apply at a single point.

    This is the 'what are the permissions/constraints for X' tool.
    """
    zones = db.zones_containing(point, when)
    if not zones:
        return {
            "point": list(point),
            "in_controlled_airspace": False,
            "permission_required": False,
            "max_altitude_m": db.regulations["max_alt_open_m"],
            "applicable_zones": [],
            "summary": "Open airspace. Recreational flight permitted up to "
                       f"{db.regulations['max_alt_open_m']}m AGL, daylight only, VLOS.",
        }

    permission = any(z.permission_required for z in zones)
    max_alt = min(z.max_drone_alt_m for z in zones)
    authorities = sorted({z.raw.get("permission_authority")
                          for z in zones if z.raw.get("permission_authority")})
    return {
        "point": list(point),
        "in_controlled_airspace": True,
        "permission_required": permission,
        "max_altitude_m": max_alt,
        "permission_authorities": authorities,
        "applicable_zones": [
            {"id": z.id, "name": z.name, "type": z.raw["type"],
             "permission_required": z.permission_required,
             "max_drone_alt_m": z.max_drone_alt_m, "notes": z.raw["notes"]}
            for z in zones
        ],
        "summary": _constraint_summary(zones, permission, max_alt, authorities),
    }


def _constraint_summary(zones, permission, max_alt, authorities) -> str:
    names = ", ".join(z.name for z in zones)
    if max_alt == 0:
        return (f"Flight NOT permitted without clearance. Inside: {names}. "
                f"Requires permission from {', '.join(authorities)}.")
    base = f"Inside {names}. Max drone altitude {max_alt}m."
    if permission:
        base += f" Permission required from {', '.join(authorities)}."
    return base


# --------------------------------------------------------------------------- #
# Computation tool: route feasibility
# --------------------------------------------------------------------------- #
@dataclass
class LegResult:
    from_point: list
    to_point: list
    distance_km: float
    blocked: bool
    reason: Optional[str]


@dataclass
class RouteResult:
    feasible: bool
    total_distance_km: float
    requested_altitude_m: int
    legs: list
    violations: list
    summary: str

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def plan_route(db: AirspaceDB, waypoints: list[Point], altitude_m: int,
               samples_per_leg: int = 12,
               when: Optional[datetime] = None) -> RouteResult:
    """Feasibility calculation across a multi-waypoint flight path.

    Samples points along each leg, checks every sample against airspace
    constraints, and aggregates blocking violations. Deterministic so the
    LLM cannot 'talk its way' past a no-fly zone.
    """
    if len(waypoints) < 2:
        raise ValueError("Route needs at least 2 waypoints.")

    legs: list[LegResult] = []
    violations: list[dict] = []
    total = 0.0

    for start, end in zip(waypoints, waypoints[1:]):
        dist = haversine_km(start, end)
        total += dist
        blocked = False
        reason = None

        for s in range(samples_per_leg + 1):
            t = s / samples_per_leg
            sample = (start[0] + (end[0] - start[0]) * t,
                      start[1] + (end[1] - start[1]) * t)
            c = query_constraints(db, sample, when)
            if c["max_altitude_m"] < altitude_m or (
                    c["permission_required"] and c["max_altitude_m"] == 0):
                blocked = True
                zone_names = [z["name"] for z in c["applicable_zones"]]
                reason = (f"Altitude {altitude_m}m exceeds limit "
                          f"{c['max_altitude_m']}m in {', '.join(zone_names)}")
                violations.append({
                    "leg": [list(start), list(end)],
                    "at_point": list(sample),
                    "reason": reason,
                    "zones": zone_names,
                })
                break

        legs.append(LegResult(list(start), list(end), round(dist, 3),
                              blocked, reason))

    feasible = len(violations) == 0
    if feasible:
        summary = (f"Route feasible: {len(legs)} legs, "
                   f"{round(total, 2)}km total at {altitude_m}m AGL.")
    else:
        summary = (f"Route NOT feasible: {len(violations)} violation(s). "
                   f"First: {violations[0]['reason']}.")

    return RouteResult(feasible, round(total, 3), altitude_m,
                       [asdict(l) for l in legs], violations, summary)
