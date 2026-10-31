> **Superseded (2026-10-28).** Historical record, kept unchanged below. It is not the current state of the
> project. Current behaviour: `README.md`; change history and decisions: `.kiro/specs/`; document status:
> `docs/README.md`.

# Project Implementation & Workflow Summary

This document summarizes our recent implementations, the workflows we have established, and details the specific problem we are facing with our Model Context Protocol (MCP) servers.

## 1. What We Have Built (Current State)
We are building the `Operation Journey Friction Reduction Agent`, which relies on multiple MCP servers to fetch data, compute metrics, and analyze user journeys for "friction".

### 1.1 Data Source & Configuration
- **DuckDB**: We use DuckDB as our in-memory analytic database. 
- **Data Configuration (`config.py`)**: Centralizes configuration, reading from `data/events.parquet` (demo mode) or `data/cji.duckdb` (realtime mode).
- **Parquet File**: We have a synthetic dataset (`data/events.parquet`, ~2.1MB) containing mock user journey events.

### 1.2 MCP Servers (`mcp_servers/`)
We broke down the agent capabilities into specific FastMCP servers:
- **`journey_data_server.py`**: Reads raw data from DuckDB. Currently exposes `get_system_info`, `get_step_metrics`, `get_funnel_dropoff`, `query_events`, and `get_live_snapshot`.
- **`friction_engine_server.py`**: Contains heuristics to detect conversion drop-offs based on the journey data.
- **`insight_server.py`**: Gleans insights and suggestions.
- **`report_server.py`**: Generates reports.

### 1.3 Client & Coordination (`tools/mcp_client.py`)
- We implemented an async Python client using the `mcp.client.stdio` library.
- Given an MCP server name (e.g., `cji-journey-data`), it spins up the server process over `STDIO` with `FastMCP` and proxies JSON-RPC queries to it.

---

## 2. Workflows & Testing Carried Out
We have been iterating on making the FastMCP servers communicate with our Python client successfully on Windows.
- **Data Generation**: We auto-generated parquet data through `synthetic_data.py`.
- **Standard execution tests**: We verified `duckdb` can read `events.parquet` locally in Python without issues.
- **MCP Client/Server tests**: We tested pinging the MCP server via `mcp_client.py` and `npx @modelcontextprotocol/inspector`.

---

## 3. The Core Problem We Are Facing

### The Symptoms
When the client attempts to call a tool that accesses the DuckDB database via the `cji-journey-data` MCP server, we experience one of two severe failures:
1. **Total Hang/Deadlock** (when tools were synchronous `def`): The client waits infinitely, and the server gets stuck indefinitely on querying duckdb. 
2. **Abrupt Crash / BrokenResourceError** (when tools were changed to `async def`): The client gets an `anyio.BrokenResourceError` and the server process exits violently (Exit code 1) meaning the STDIO pipes break immediately upon executing a query.

### Root Cause Analysis
The error is caused by a **collision between FastMCP's communication model (JSON-RPC over STDIO) and DuckDB's native multithreading / C-extension behavior on Windows.**

Here are the specific factors interacting to cause the bug:
1. **STDIO Hijacking**: FastMCP relies heavily on intercepting `stdin` and `stdout` to communicate using the JSON-RPC standard. It redirects `stdout` to `stderr` internally to avoid polluting JSON outputs. 
2. **DuckDB Blocks**: By default, FastMCP runs synchronous tools (`def`) inside an internal Python `ThreadPoolExecutor`. When multiple operations interact through Python's `asyncio` event loop while a C-extension (DuckDB) holds its own threads and locks on Windows filesystem files, a deadlock occurs.
3. **Async C-Extension Crash**: To avoid the threadpool, we shifted the tool methods to `async def`, which forces them to execute directly on the main event loop. However, DuckDB makes blocking IO and standard C-level database calls. Making blocking C-extension calls inside Python's single-threaded event-loop caused FastMCP's internal protocol loops (the ones feeding `stdin`/`stdout`) to starve and break, or triggered an internal process segmentation fault/panic in DuckDB that crashes the server entirely (Exit Code 1).

### The "Friction" Server Counter-Test
We verified this exact root cause by querying `cji-friction-engine` (a different FastMCP server that does **not** initialize DuckDB yet). The friction server successfully responded with an MCP error message (`Unknown tool`) and cleanly returned without crashing or hanging. This undeniably proves the MCP client works perfectly, and the crash is highly specific to DuckDB integration.

### Proposed Solutions moving forward
To resolve this error, we must decouple the `DuckDB` execution model from the `FastMCP STDIO` transport:
- **Solution A**: Host the MCP server over HTTP/SSE instead of STDIO. This frees up standard in/out streams so `duckdb` doesn't inadvertently crash the process pipes, and keeps local networking clean without deadlock.
- **Solution B**: Try instantiating duckdb differently (e.g., using `duckdb.execute` instead of creating long-lived connection objects) or explicitly wrapping duckdb calls inside cleanly isolated processes.
