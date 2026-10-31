"""
cji-servers: starts every MCP service in the settings registry (Spec 04).
Ports and transport come from the registry, not from this file. Each server runs as
`python -m cji.mcp_servers.<name>` in the runtime home (CJI_HOME, Spec 11).
"""
import argparse
import logging
import os
import subprocess
import sys

from cji.logs import configure_logging
from cji.settings import ConfigError, get_settings, require

logger = logging.getLogger(__name__)


def launch_plan() -> list[tuple[str, str]]:
    """(logical name, module) for every MCP service, in registry order."""
    return [(e.name, e.launch) for e in get_settings().services.mcp_services() if e.launch]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cji-servers", description="CJI MCP Server Launcher")
    parser.add_argument(
        "--mode", choices=["demo", "realtime"], default=None,
        help="Override CJI_MODE for all servers (demo or realtime)."
    )
    args = parser.parse_args(argv)
    configure_logging(fmt="%(asctime)s [%(levelname)s] %(message)s")

    # Inject mode override if supplied (before settings are first loaded)
    if args.mode:
        os.environ["CJI_MODE"] = args.mode
        logger.info(f"CJI_MODE overridden to: {args.mode}")
    else:
        logger.info(f"CJI_MODE from env: {os.environ.get('CJI_MODE', 'demo (default)')}")

    try:
        settings = require(get_settings(), "launcher")
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2

    home = settings.storage.home
    env = {**os.environ, "CJI_HOME": str(home)}    # children resolve data/ and .env in the same home

    processes = []
    logger.info("Starting MCP servers...")
    try:
        for name, module_name in launch_plan():
            endpoint = settings.services.get(name)
            logger.info(f"Spawning {module_name} ({name} on {endpoint.host}:{endpoint.port}, {endpoint.transport})...")
            p = subprocess.Popen(
                [sys.executable, "-m", module_name],
                cwd=str(home),
                env=env,
            )
            processes.append((module_name, p))

        logger.info("All servers spawned. Press Ctrl+C to stop.")

        # Wait indefinitely for processes
        for name, p in processes:
            p.wait()

    except KeyboardInterrupt:
        logger.info("\nShutting down servers...")
    finally:
        for name, p in processes:
            if p.poll() is None:
                logger.info(f"Terminating {name}...")
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        logger.info("Shutdown complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
