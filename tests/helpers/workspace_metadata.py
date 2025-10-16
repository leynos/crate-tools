"""Helper utilities for workspace metadata tests."""

from __future__ import annotations

import textwrap
import typing as typ
from pathlib import Path


def _create_test_manifest(workspace_root: Path, crate_name: str, content: str) -> Path:
    """Write a manifest for ``crate_name`` beneath ``workspace_root``."""

    manifest_dir = workspace_root / crate_name
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "Cargo.toml"
    manifest_path.write_text(textwrap.dedent(content).strip())
    return manifest_path


def _create_test_package_metadata(
    name: str,
    version: str,
    manifest_path: Path,
    dependencies: list[dict[str, str]] | None = None,
    publish: list[str] | None = None,
) -> dict[str, typ.Any]:
    """Create package metadata with predictable identifiers for tests."""

    normalized_dependencies = list(dependencies) if dependencies is not None else []
    normalized_publish = [] if publish is None else list(publish)
    return {
        "name": name,
        "version": version,
        "id": f"{name}-id",
        "manifest_path": str(manifest_path),
        "dependencies": normalized_dependencies,
        "publish": normalized_publish,
    }
