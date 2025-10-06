"""Pytest configuration for the lading test-suite."""

from __future__ import annotations

import os
import typing as typ
from pathlib import Path

import pytest

pytest_plugins = ("cmd_mox.pytest_plugin",)


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _restore_workspace_env() -> typ.Iterator[None]:
    """Ensure tests do not leak ``LADING_WORKSPACE_ROOT`` between runs."""
    from lading.cli import WORKSPACE_ROOT_ENV_VAR

    original = os.environ.get(WORKSPACE_ROOT_ENV_VAR)
    try:
        yield
    finally:
        if original is None:
            os.environ.pop(WORKSPACE_ROOT_ENV_VAR, None)
        else:
            os.environ[WORKSPACE_ROOT_ENV_VAR] = original
