"""Lading CLI package.

This package initialises the Cyclopts application and exposes the
:func:`lading.cli.main` entry point for process launchers.
"""

from __future__ import annotations

from .cli import app, main

__all__ = ["app", "main"]
