"""MCP server exposing the airspace dataset + computation tools to an LLM.

Built with the official `mcp` SDK. Person E's query/compute functions are
registered here as callable tools. Run with:  python -m src.server
"""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .data_layer import AirspaceDB
from .compute import query_constraints, plan_route

db = AirspaceDB()
mcp = FastMCP("aviation-airspace")


@mcp.tool()
def list_zones() -> str:
    """List all known airspace zones with their type and permission status."""
    zones = [
        {"id": z.id, "name": z.name, "type": z.raw["type"],
         "permission_required": z.permission_required,
         "max_drone_alt_m": z.max_drone_alt_m}
        for z in db.all_zones()
    ]
    return json.dumps(zones, indent=2)


@mcp.tool()
def get_constraints(lat: float, lon: float) -> str:
    """Get drone-flight constraints (permissions, max altitude, authorities)
    that apply at a given latitude/longitude."""
    return json.dumps(query_constraints(db, (lat, lon)), indent=2)


@mcp.tool()
def check_route(waypoints: list[list[float]], altitude_m: int) -> str:
    """Check whether a drone route is feasible at a given altitude.

    waypoints: list of [lat, lon] pairs (>= 2). Returns per-leg feasibility,
    total distance, and any airspace violations.
    """
    pts = [(float(p[0]), float(p[1])) for p in waypoints]
    result = plan_route(db, pts, int(altitude_m))
    return json.dumps(result.to_dict(), indent=2)


if __name__ == "__main__":
    mcp.run()
