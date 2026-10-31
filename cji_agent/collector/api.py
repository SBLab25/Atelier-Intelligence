"""Compatibility launcher: `uvicorn collector.api:app` = `uvicorn cji.collector.api:app` (Spec 11, OD-98)."""
from cji.collector.api import app

__all__ = ["app"]
