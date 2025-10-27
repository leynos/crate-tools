"""Manifest-related behavioural fixtures for CLI scenarios."""

from __future__ import annotations

import typing as typ

from pytest_bdd import given, parsers
from tomlkit import parse as parse_toml

if typ.TYPE_CHECKING:
    from pathlib import Path


def _update_manifest_version(
    manifest_path: Path,
    version: str,
    keys: tuple[str, ...],
) -> None:
    """Update version at nested ``keys`` path in the manifest at ``manifest_path``."""
    if not manifest_path.exists():
        message = f"Manifest not found: {manifest_path}"
        raise AssertionError(message)
    document = parse_toml(manifest_path.read_text(encoding="utf-8"))
    target = document
    for key in keys[:-1]:
        try:
            target = target[key]
        except KeyError as exc:  # pragma: no cover - defensive guard
            path = "/".join(keys)
            message = f"Key path {path!r} missing from manifest {manifest_path}"
            raise AssertionError(message) from exc
    target[keys[-1]] = version
    manifest_path.write_text(document.as_string(), encoding="utf-8")


def _update_crate_manifests(crates_root: Path, version: str) -> None:
    """Update version in all crate manifests under ``crates_root``."""
    if not crates_root.exists():
        message = f"Crates directory not found: {crates_root}"
        raise AssertionError(message)
    for child in crates_root.iterdir():
        if not child.is_dir():
            continue
        manifest_path = child / "Cargo.toml"
        _update_manifest_version(
            manifest_path,
            version,
            ("package", "version"),
        )


@given(parsers.parse('the workspace manifests record version "{version}"'))
def given_workspace_versions_match(
    workspace_directory: Path,
    version: str,
) -> None:
    """Ensure the workspace and member manifests record ``version``."""
    workspace_manifest = workspace_directory / "Cargo.toml"
    _update_manifest_version(
        workspace_manifest,
        version,
        ("workspace", "package", "version"),
    )
    crates_root = workspace_directory / "crates"
    _update_crate_manifests(crates_root, version)
