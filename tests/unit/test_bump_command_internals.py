"""Internal unit tests for the :mod:`lading.commands.bump` module internals."""

from __future__ import annotations

import typing as typ

from tomlkit import parse as parse_toml

from lading.commands import bump
from lading.workspace import WorkspaceCrate, WorkspaceDependency, WorkspaceGraph
from tests.unit.conftest import _load_version, _make_config

if typ.TYPE_CHECKING:
    from pathlib import Path


def _make_test_crate_with_dependency(
    tmp_path: Path,
    *,
    crate_name: str = "beta",
    crate_version: str = "0.1.0",
    dependency: tuple[str, str] = ("alpha", "0.1.0"),
) -> WorkspaceCrate:
    """Create a test crate manifest with a single dependency.

    Args:
        tmp_path: Directory where the manifest will be created.
        crate_name: Name of the crate to create.
        crate_version: Version of the crate.
        dependency: Tuple of (dependency_name, dependency_version).

    """
    dependency_name, dependency_version = dependency
    manifest_path = tmp_path / "Cargo.toml"
    manifest_path.write_text(
        f"""
        [package]
        name = "{crate_name}"
        version = "{crate_version}"

        [dependencies]
        {dependency_name} = "{dependency_version}"
        """,
        encoding="utf-8",
    )
    return WorkspaceCrate(
        id=f"{crate_name}-id",
        name=crate_name,
        version=crate_version,
        manifest_path=manifest_path,
        root_path=manifest_path.parent,
        publish=True,
        readme_is_workspace=False,
        dependencies=(
            WorkspaceDependency(
                package_id=f"{dependency_name}-id",
                name=dependency_name,
                manifest_name=dependency_name,
                kind=None,
            ),
        ),
    )


def _make_workspace_with_alpha_dependency(
    tmp_path: Path,
    *,
    dependency: tuple[str, str] = ("alpha", "0.1.0"),
) -> tuple[WorkspaceCrate, WorkspaceGraph]:
    """Create a workspace with beta crate depending on alpha crate.

    Args:
        tmp_path: Directory where manifests will be created.
        dependency: Tuple of (dependency_name, dependency_version) for beta's
            dependency.

    Returns:
        Tuple of (beta_crate, workspace_graph).

    """
    beta_crate = _make_test_crate_with_dependency(tmp_path, dependency=dependency)

    alpha_manifest = tmp_path / "alpha" / "Cargo.toml"
    alpha_manifest.parent.mkdir(parents=True, exist_ok=True)
    alpha_manifest.write_text(
        '[package]\nname = "alpha"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    alpha_crate = WorkspaceCrate(
        id="alpha-id",
        name="alpha",
        version="0.1.0",
        manifest_path=alpha_manifest,
        root_path=alpha_manifest.parent,
        publish=True,
        readme_is_workspace=False,
        dependencies=(),
    )

    workspace = WorkspaceGraph(
        workspace_root=tmp_path,
        crates=(beta_crate, alpha_crate),
    )

    return beta_crate, workspace


def test_update_crate_manifest_skips_version_bump_for_excluded_crate(
    tmp_path: Path,
) -> None:
    """Excluded crates keep their version while dependency requirements refresh."""
    crate, workspace = _make_workspace_with_alpha_dependency(tmp_path)
    options = bump.BumpOptions(
        configuration=_make_config(exclude=("beta",)),
        workspace=workspace,
    )

    changed = bump._update_crate_manifest(
        crate,
        "1.2.3",
        options,
    )

    assert changed is True
    document = parse_toml(crate.manifest_path.read_text(encoding="utf-8"))
    assert document["package"]["version"] == "0.1.0"
    assert document["dependencies"]["alpha"].value == "1.2.3"


def test_update_crate_manifest_updates_version_and_dependencies(
    tmp_path: Path,
) -> None:
    """Crate manifests receive the new version and dependency updates."""
    crate, workspace = _make_workspace_with_alpha_dependency(
        tmp_path,
        dependency=("alpha", "^0.1.0"),
    )
    options = bump.BumpOptions(
        configuration=_make_config(),
        workspace=workspace,
    )

    changed = bump._update_crate_manifest(
        crate,
        "1.2.3",
        options,
    )

    assert changed is True
    document = parse_toml(crate.manifest_path.read_text(encoding="utf-8"))
    assert document["package"]["version"] == "1.2.3"
    assert document["dependencies"]["alpha"].value == "^1.2.3"


def test_format_result_message_handles_changes(tmp_path: Path) -> None:
    """The formatted result message reflects manifest counts and paths."""
    workspace_root = tmp_path
    manifest_paths = [
        workspace_root / "Cargo.toml",
        workspace_root / "member" / "Cargo.toml",
    ]
    assert (
        bump._format_result_message(
            [], "1.2.3", dry_run=False, workspace_root=workspace_root
        )
        == "No manifest changes required; all versions already 1.2.3."
    )
    assert bump._format_result_message(
        manifest_paths,
        "4.5.6",
        dry_run=False,
        workspace_root=workspace_root,
    ).splitlines() == [
        "Updated version to 4.5.6 in 2 manifest(s):",
        "- Cargo.toml",
        "- member/Cargo.toml",
    ]
    assert bump._format_result_message(
        manifest_paths,
        "4.5.6",
        dry_run=True,
        workspace_root=workspace_root,
    ).splitlines() == [
        "Dry run; would update version to 4.5.6 in 2 manifest(s):",
        "- Cargo.toml",
        "- member/Cargo.toml",
    ]


def test_update_manifest_writes_when_changed(tmp_path: Path) -> None:
    """Applying a new version persists changes to disk."""
    manifest_path = tmp_path / "Cargo.toml"
    manifest_path.write_text('[package]\nname = "demo"\nversion = "0.1.0"\n')
    changed = bump._update_manifest(
        manifest_path, (("package",),), "1.0.0", bump.BumpOptions()
    )
    assert changed is True
    assert _load_version(manifest_path, ("package",)) == "1.0.0"


def test_update_manifest_preserves_inline_comment(tmp_path: Path) -> None:
    """Inline comments survive manifest rewrites."""
    manifest_path = tmp_path / "Cargo.toml"
    manifest_path.write_text(
        '[package]\nversion = "0.1.0"  # keep me\n', encoding="utf-8"
    )
    changed = bump._update_manifest(
        manifest_path, (("package",),), "1.2.3", bump.BumpOptions()
    )
    assert changed is True
    text = manifest_path.read_text(encoding="utf-8")
    assert "# keep me" in text
    document = parse_toml(text)
    assert document["package"]["version"] == "1.2.3"


def test_update_manifest_skips_when_unchanged(tmp_path: Path) -> None:
    """No write occurs when the manifest already records the target version."""
    manifest_path = tmp_path / "Cargo.toml"
    original = '[package]\nname = "demo"\nversion = "0.1.0"\n'
    manifest_path.write_text(original)
    changed = bump._update_manifest(
        manifest_path, (("package",),), "0.1.0", bump.BumpOptions()
    )
    assert changed is False
    assert manifest_path.read_text() == original


def test_select_table_returns_nested_table() -> None:
    """Select nested tables using dotted selectors."""
    document = parse_toml('[workspace]\n[workspace.package]\nversion = "0.1.0"\n')
    table = bump._select_table(document, ("workspace", "package"))
    assert table is document["workspace"]["package"]


def test_select_table_returns_none_for_missing() -> None:
    """Selectors that do not resolve to tables return ``None``."""
    document = parse_toml("[workspace]\nmembers = []\n")
    table = bump._select_table(document, ("workspace", "package"))
    assert table is None


def test_assign_version_handles_absent_table() -> None:
    """``_assign_version`` tolerates missing tables."""
    assert bump._assign_version(None, "1.0.0") is False


def test_assign_version_updates_value() -> None:
    """Assign a new version when the stored value differs."""
    table = parse_toml('[package]\nname = "demo"\nversion = "0.1.0"\n')["package"]
    assert bump._assign_version(table, "2.0.0") is True
    assert table["version"] == "2.0.0"


def test_assign_version_detects_existing_value() -> None:
    """Return ``False`` when the version already matches."""
    table = parse_toml('[package]\nversion = "0.1.0"\n')["package"]
    assert bump._assign_version(table, "0.1.0") is False


def test_value_matches_accepts_plain_strings() -> None:
    """Strings compare directly when checking for version matches."""
    assert bump._value_matches("1.0.0", "1.0.0") is True
    assert bump._value_matches("1.0.0", "2.0.0") is False


def test_value_matches_handles_toml_items() -> None:
    """TOML items compare via their stored string value."""
    document = parse_toml('version = "3.0.0"')
    item = document["version"]
    assert bump._value_matches(item, "3.0.0") is True
    assert bump._value_matches(item, "4.0.0") is False
