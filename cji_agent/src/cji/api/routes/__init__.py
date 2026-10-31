"""The /api/v1 routes (Spec 12, design §3)."""
from __future__ import annotations

from fastapi import APIRouter

from . import health, ingestions, journeys, reports, runs
from ._deps import API_PREFIX

router = APIRouter(prefix=API_PREFIX)
for _module in (health, journeys, reports, runs):
    router.include_router(_module.router)

# Write operations of Spec 14 (start, resume, ingestion): mounted unless CJI_API_WRITE_OPERATIONS=false.
write_router = APIRouter(prefix=API_PREFIX)
write_router.include_router(runs.write_router)
write_router.include_router(ingestions.router)

__all__ = ["router", "write_router"]
