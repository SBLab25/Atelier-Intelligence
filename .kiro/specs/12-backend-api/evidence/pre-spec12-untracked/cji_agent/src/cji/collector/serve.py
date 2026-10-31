"""
cji-collector: serve the collector API (cji.collector.api:app) with uvicorn on the configured collector endpoint
(CJI_COLLECTOR_URL / CJI_COLLECTOR_PORT, service registry). Spec 11, OD-97.
"""
from __future__ import annotations

import argparse
import sys

from cji.logs import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cji-collector",
        description="Run the CJI collector (FastAPI) with uvicorn on the configured collector endpoint.",
    )
    parser.add_argument("--host", default=None, help="bind address (default: the configured collector host)")
    parser.add_argument("--port", type=int, default=None, help="port (default: the configured collector port)")
    args = parser.parse_args(argv)
    configure_logging()
    from cji.settings import ConfigError, get_settings

    try:
        endpoint = get_settings().services.get("collector")
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    import uvicorn

    uvicorn.run("cji.collector.api:app", host=args.host or endpoint.host, port=args.port or endpoint.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
