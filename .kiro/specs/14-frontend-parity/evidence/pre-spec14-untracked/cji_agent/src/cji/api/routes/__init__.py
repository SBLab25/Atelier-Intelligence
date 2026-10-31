"""The /api/v1 routes (Spec 12, design §3)."""
from __future__ import annotations

from fastapi import APIRouter

from . import health, journeys, reports, runs
from ._deps import API_PREFIX

router = APIRouter(prefix=API_PREFIX)
for _module in (health, journeys, reports, runs):
    router.include_router(_module.router)

__all__ = ["router"]
