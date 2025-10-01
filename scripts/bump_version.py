"""Compatibility wrapper for :mod:`crate_tools.bump_version`."""

from __future__ import annotations

from crate_tools.bump_version import (
    _update_dependency_version,
    _update_markdown_versions,
    main,
    replace_fences,
    replace_version_in_toml,
)

__all__ = [
    "_update_dependency_version",
    "_update_markdown_versions",
    "main",
    "replace_fences",
    "replace_version_in_toml",
]

if __name__ == "__main__":  # pragma: no cover - import-time compatibility shim
    import sys

    raise SystemExit(main(sys.argv))
