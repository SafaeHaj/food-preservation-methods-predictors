"""Combines all v1 endpoint routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import extraction, prediction, query, survival

api_router = APIRouter()
api_router.include_router(extraction.router)
api_router.include_router(query.router)
api_router.include_router(prediction.router)
api_router.include_router(survival.router)
