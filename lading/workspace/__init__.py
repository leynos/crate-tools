"""Workspace discovery utilities for :mod:`lading`."""

from __future__ import annotations

from .metadata import CargoMetadataError, load_cargo_metadata

__all__ = ["CargoMetadataError", "load_cargo_metadata"]
