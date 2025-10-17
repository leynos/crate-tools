"""Helper utilities for workspace metadata tests."""

from __future__ import annotations

__all__ = ["_build_test_package", "_create_test_manifest"]

import textwrap
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path


def _create_test_manifest(workspace_root: Path, crate_name: str, content: str) -> Path:
    """Write a manifest for ``crate_name`` beneath ``workspace_root``."""
    manifest_dir = workspace_root / crate_name
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "Cargo.toml"
    manifest_path.write_text(textwrap.dedent(content).strip())
    return manifest_path


def _build_test_package(
    name: str,
    version: str,
    manifest_path: Path,
    **kwargs: object,
) -> dict[str, typ.Any]:
    """Create package metadata with predictable identifiers for tests.

    Args:
        name: Package name
        version: Package version
        manifest_path: Path to the manifest file
        **kwargs: Optional fields (dependencies, publish, etc.)

    """
    return {
        "name": name,
        "version": version,
        "id": f"{name}-id",
        "manifest_path": str(manifest_path),
        "dependencies": kwargs.get("dependencies", []),
        "publish": kwargs.get("publish"),
    }
