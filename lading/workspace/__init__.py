"""Workspace discovery utilities for :mod:`lading`."""

from __future__ import annotations

from .metadata import (
    CargoExecutableNotFoundError,
    CargoMetadataError,
    load_cargo_metadata,
)

__all__ = [
    "CargoExecutableNotFoundError",
    "CargoMetadataError",
    "load_cargo_metadata",
]
