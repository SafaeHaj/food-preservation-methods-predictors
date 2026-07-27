"""Shared providers reused across the app and API dependency injection."""

from __future__ import annotations

from app.core.config import Config, Settings, get_config, get_settings

__all__ = ["Settings", "Config", "get_settings", "get_config"]
