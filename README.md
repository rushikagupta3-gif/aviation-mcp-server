# Aviation Airspace MCP Server

A Model Context Protocol (MCP) server that exposes a structured airspace
dataset to an LLM via tool-calling, with a deterministic **route-feasibility
computation tool** and a **safety test suite** that prevents unintended
(unsafe) actions.

> **My role (Person E):** the LLM query layer (`get_constraints`), the callable
> computation tool (`check_route`), and the tool-calling orchestration through
> the MCP server. Built on a shared data layer.

## What it does

| Tool | Purpose |
|------|---------|
| `list_zones` | List all airspace zones + permission status |
| `get_constraints(lat, lon)` | "What are the permissions/constraints for X" |
| `check_route(waypoints, altitude_m)` | Route feasibility calc across a flight path |

The computation is **pure and deterministic**, so the LLM cannot talk its way
past a no-fly zone — the route checker independently blocks any path that
enters controlled/restricted airspace or exceeds altitude limits.

## Run it

```bash
pip install -r requirements.txt
python -m src.server        # starts the MCP server (stdio transport)
```

Connect it to any MCP client (Claude Desktop, etc.) by pointing the client at
`python -m src.server` in this directory.

## Test it

```bash
pytest tests/ -v             # 9 safety + reliability tests, all green
```

## Architecture

```
data/airspace.json     real airspace zones + regulations
src/data_layer.py      loading, geo (haversine), zone containment
src/compute.py         query_constraints + plan_route  <-- Person E core
src/server.py          MCP tool registration
tests/test_safety.py   no-fly-zone + altitude + edge-case guards
```

## CV line

> Built a Model Context Protocol (MCP) server exposing airspace data to LLMs
> via tool-calling, with a route-feasibility computation tool and a safety
> test suite preventing unintended actions.
