"""Streamlit UI for the Aviation MCP Server — Airspace Tools.

Three tabs:
  - Zone Explorer      : browse all loaded airspace zones
  - Constraint Lookup  : query constraints at a lat/lon point
  - Route Feasibility  : run a full preflight check on a waypoint list

Run:  streamlit run src/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_layer import AirspaceDB
from src.compute import query_constraints
from validators import validate_coordinates, validate_altitude, validate_waypoints
from workflows import run_preflight_check

# --------------------------------------------------------------------------- #
# Page config
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Aviation MCP Server",
    page_icon="✈",
    layout="wide",
)

st.markdown("""
<style>
    .block-container { padding-top: 2rem; max-width: 1100px; }
    .zone-badge {
        display: inline-block;
        padding: 2px 8px; border-radius: 4px;
        font-size: 0.78rem; font-weight: 600; color: #fff;
    }
    .badge-controlled   { background: #d62728; }
    .badge-restricted   { background: #e6550d; }
    .badge-open         { background: #2ca02c; }
    .badge-temporary    { background: #9467bd; }
</style>
""", unsafe_allow_html=True)

st.title("Aviation MCP Server")
st.caption("Singapore drone airspace — zone data, constraint lookup, and route feasibility")
st.divider()

# --------------------------------------------------------------------------- #
# Shared state: load DB once
# --------------------------------------------------------------------------- #
@st.cache_resource
def load_db() -> AirspaceDB:
    return AirspaceDB()


try:
    db = load_db()
except Exception as exc:
    st.error(f"Failed to load airspace database: {exc}")
    st.stop()

# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab_zones, tab_constraints, tab_route = st.tabs([
    "Zone Explorer",
    "Constraint Lookup",
    "Route Feasibility Checker",
])

# =========================================================================== #
# TAB 1 — Zone Explorer
# =========================================================================== #
with tab_zones:
    st.subheader("Airspace Zones")
    st.write("All zones loaded from the airspace database.")

    zones = db.all_zones()

    # Build display rows
    rows = []
    for z in zones:
        rows.append({
            "ID": z.id,
            "Name": z.name,
            "Type": z.raw.get("type", "—"),
            "Max Altitude (m)": z.max_drone_alt_m,
            "Permission Required": "Yes" if z.permission_required else "No",
            "Authority": z.raw.get("permission_authority") or "—",
            "Notes": z.raw.get("notes", ""),
        })

    import pandas as pd
    df = pd.DataFrame(rows)

    # Summary metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Zones", len(zones))
    m2.metric("Restricted / Controlled",
              sum(1 for z in zones if z.permission_required))
    m3.metric("Open (No Permit)", sum(1 for z in zones if not z.permission_required))

    st.divider()
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Max Altitude (m)": st.column_config.NumberColumn(format="%d m"),
            "Permission Required": st.column_config.TextColumn(),
        },
    )

    with st.expander("Raw zone details"):
        import json
        for z in zones:
            st.markdown(f"**{z.name}** (`{z.id}`)")
            st.json(z.raw)

# =========================================================================== #
# TAB 2 — Constraint Lookup
# =========================================================================== #
with tab_constraints:
    st.subheader("Constraint Lookup")
    st.write("Enter a coordinate to see which airspace rules apply at that point.")

    col_lat, col_lon = st.columns(2)
    with col_lat:
        lat_input = st.number_input(
            "Latitude", value=1.2806, min_value=-90.0, max_value=90.0,
            format="%.6f", step=0.0001,
            help="Decimal degrees, e.g. 1.2806",
        )
    with col_lon:
        lon_input = st.number_input(
            "Longitude", value=103.8636, min_value=-180.0, max_value=180.0,
            format="%.6f", step=0.0001,
            help="Decimal degrees, e.g. 103.8636",
        )

    if st.button("Look up constraints", type="primary"):
        try:
            validate_coordinates(lat_input, lon_input)
            result = query_constraints(db, (lat_input, lon_input))

            st.divider()
            r1, r2, r3 = st.columns(3)
            r1.metric("Max Altitude", f"{result['max_altitude_m']} m")
            r2.metric("Controlled Airspace",
                      "Yes" if result["in_controlled_airspace"] else "No")
            r3.metric("Permission Required",
                      "Yes" if result["permission_required"] else "No")

            st.divider()
            if result["permission_required"]:
                authorities = result.get("permission_authorities", [])
                st.error(
                    f"Permission required from: **{', '.join(authorities) or 'unknown authority'}**"
                )
            else:
                st.success("No permission required — open airspace at this point.")

            st.info(f"**Summary:** {result['summary']}")

            applicable = result.get("applicable_zones", [])
            if applicable:
                st.markdown(f"**Applicable zones ({len(applicable)}):**")
                for z in applicable:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 1, 2])
                        c1.markdown(f"**{z['name']}** `{z['id']}`")
                        c2.markdown(f"Type: `{z['type']}`")
                        c3.markdown(f"Max: **{z['max_drone_alt_m']} m** · Permit: {'Yes' if z['permission_required'] else 'No'}")
                        if z.get("notes"):
                            st.caption(z["notes"])
            else:
                st.markdown("No specific zone — open airspace applies.")

        except ValueError as exc:
            st.error(f"Invalid input: {exc}")
        except Exception as exc:
            st.error(f"Lookup failed: {exc}")

# =========================================================================== #
# TAB 3 — Route Feasibility Checker
# =========================================================================== #
with tab_route:
    st.subheader("Route Feasibility Checker")
    st.write("Enter waypoints (one `lat, lon` pair per line) and a flight altitude.")

    col_wp, col_alt = st.columns([3, 1])

    with col_wp:
        waypoints_raw = st.text_area(
            "Waypoints (lat, lon — one per line)",
            value="1.2806, 103.8636\n1.2810, 103.8640",
            height=160,
            help="Example:\n1.2806, 103.8636\n1.3644, 103.9915",
        )

    with col_alt:
        altitude_input = st.number_input(
            "Altitude (m AGL)",
            value=50,
            min_value=1,
            max_value=5000,
            step=5,
            help="Altitude above ground level in metres",
        )

    if st.button("Check route", type="primary"):
        # Parse waypoints safely
        waypoints: list[list[float]] = []
        parse_error: str | None = None

        for i, line in enumerate(waypoints_raw.strip().splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != 2:
                parse_error = (
                    f"Line {i} — expected 'lat, lon' but got: '{line}'"
                )
                break
            try:
                waypoints.append([float(parts[0].strip()), float(parts[1].strip())])
            except ValueError:
                parse_error = f"Line {i} — could not parse numbers from: '{line}'"
                break

        if parse_error:
            st.error(f"Waypoint parse error: {parse_error}")
        else:
            try:
                validate_waypoints(waypoints)
                validate_altitude(altitude_input)
                result = run_preflight_check(db, waypoints, altitude_input)

                st.divider()
                status = result["status"]

                # Top-level verdict
                if status == "approved":
                    st.success(f"Route **APPROVED** — {result['recommendation']}")
                else:
                    st.error(f"Route **REJECTED** — {result['recommendation']}")

                # Metrics row
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Status", status.upper())
                m2.metric("Altitude", f"{result['checked_altitude_m']} m AGL")
                m3.metric("Total Distance", f"{result['total_distance_km']} km")
                m4.metric("Violations", len(result["violations"]))

                # Violations detail
                violations = result["violations"]
                if violations:
                    st.divider()
                    st.markdown(f"**Violations ({len(violations)}):**")
                    for v in violations:
                        with st.container(border=True):
                            st.markdown(f"Reason: {v['reason']}")
                            st.caption(
                                f"At point: {v['at_point']}  ·  "
                                f"Leg: {v['leg'][0]} → {v['leg'][1]}  ·  "
                                f"Zones: {', '.join(v['zones'])}"
                            )

                # Per-waypoint constraints expander
                wc = result.get("waypoint_constraints", [])
                if wc:
                    with st.expander("Per-waypoint constraint details"):
                        for idx, c in enumerate(wc):
                            st.markdown(
                                f"**Waypoint {idx + 1}** "
                                f"`{c['point']}`  —  {c['summary']}"
                            )

            except ValueError as exc:
                st.error(f"Validation error: {exc}")
            except Exception as exc:
                st.error(f"Route check failed: {exc}")
