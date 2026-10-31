"""
cji-api: serve the /api/v1 backend (cji.api.app:app) with uvicorn on the configured `api` endpoint
(CJI_API_URL / CJI_API_PORT, default port 8006). Spec 12, OD-108.
"""
from __future__ import annotations

import argparse
import sys

from cji.logs import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cji-api",
        description="Run the CJI backend API (/api/v1, FastAPI) with uvicorn on the configured api endpoint. "
                    "Tokens: cji-api-token.",
    )
    parser.add_argument("--host", default=None, help="bind address (default: the configured api host)")
    parser.add_argument("--port", type=int, default=None, help="port (default: the configured api port)")
    args = parser.parse_args(argv)
    configure_logging(service="cji-api")
    from cji.settings import ConfigError, get_settings
    from cji.settings.roles import require

    try:
        settings = require(get_settings(), "api")
        endpoint = settings.services.get("api")
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    import uvicorn

    uvicorn.run("cji.api.app:app", host=args.host or endpoint.host, port=args.port or endpoint.port,
                log_config=None)   # uvicorn's loggers use the CJI handler (JSON in production, Spec 15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
