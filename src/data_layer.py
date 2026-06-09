"""Data access layer for the airspace dataset.

Loads zones + regulations and provides geo helpers and query primitives.
Person E owns the query layer + computation; this module is the shared data
foundation those build on.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "airspace.json"

EARTH_RADIUS_KM = 6371.0088


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points in km."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class Zone:
    raw: dict

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def name(self) -> str:
        return self.raw["name"]

    @property
    def center(self) -> tuple[float, float]:
        c = self.raw["geometry"]["center"]
        return (c[0], c[1])

    @property
    def radius_km(self) -> float:
        return float(self.raw["geometry"]["radius_km"])

    @property
    def permission_required(self) -> bool:
        return bool(self.raw["permission_required"])

    @property
    def max_drone_alt_m(self) -> int:
        return int(self.raw["max_drone_alt_m"])

    def contains(self, point: tuple[float, float]) -> bool:
        return haversine_km(self.center, point) <= self.radius_km

    def is_active(self, when: Optional[datetime] = None) -> bool:
        """Temporary zones are only active inside their window."""
        window = self.raw.get("active_window")
        if not window:
            return True
        when = when or datetime.now(timezone.utc)
        start = datetime.fromisoformat(window["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(window["end"].replace("Z", "+00:00"))
        return start <= when <= end


class AirspaceDB:
    def __init__(self, path: Path = _DATA_PATH):
        data = json.loads(Path(path).read_text())
        self.zones = [Zone(z) for z in data["zones"]]
        self.regulations = data["regulations"]

    def get_zone(self, zone_id: str) -> Optional[Zone]:
        return next((z for z in self.zones if z.id == zone_id), None)

    def zones_containing(self, point: tuple[float, float],
                         when: Optional[datetime] = None) -> list[Zone]:
        return [z for z in self.zones if z.contains(point) and z.is_active(when)]

    def all_zones(self) -> list[Zone]:
        return list(self.zones)
