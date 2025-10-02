"""Compatibility wrapper for :mod:`crate_tools.bump_version`."""

from crate_tools.bump_version import (
    main,
    replace_fences,
    replace_version_in_toml,
)

__all__ = [
    "main",
    "replace_fences",
    "replace_version_in_toml",
]

if __name__ == "__main__":  # pragma: no cover - import-time compatibility shim
    import sys

    raise SystemExit(main(sys.argv))
