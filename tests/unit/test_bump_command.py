"""Unit tests for the :mod:`lading.commands.bump` module."""

from __future__ import annotations

import dataclasses as dc
import textwrap
import typing as typ
from pathlib import Path

from tomlkit import parse as parse_toml

from lading import config as config_module
from lading.commands import bump
from lading.workspace import WorkspaceCrate, WorkspaceDependency, WorkspaceGraph

if typ.TYPE_CHECKING:
    import pytest


def _write_workspace_manifest(root: Path, members: list[str]) -> Path:
    """Create a minimal workspace manifest with the provided members."""
    manifest = root / "Cargo.toml"
    entries = ", ".join(f'"{member}"' for member in members)
    manifest.write_text(
        "[workspace]\n"
        f"members = [{entries}]\n\n"
        "[workspace.package]\n"
        'version = "0.1.0"\n'
    )
    return manifest


def _write_crate_manifest(
    manifest_path: Path,
    *,
    name: str,
    version: str,
    extra_sections: str = "",
) -> None:
    """Write a crate manifest with optional dependency sections."""
    content = textwrap.dedent(
        f"""
        [package]
        name = "{name}"
        version = "{version}"
        """
    ).lstrip()
    if extra_sections:
        content += "\n" + textwrap.dedent(extra_sections).strip() + "\n"
    manifest_path.write_text(content, encoding="utf-8")


@dc.dataclass(frozen=True, slots=True)
class _CrateSpec:
    """Specification for constructing workspace crates in tests."""

    name: str
    manifest_extra: str = ""
    dependencies: tuple[WorkspaceDependency, ...] = ()
    version: str = "0.1.0"


def _build_workspace_with_internal_deps(
    root: Path, *, specs: tuple[_CrateSpec, ...]
) -> tuple[WorkspaceGraph, dict[str, Path]]:
    """Create a workspace populated with crates and return manifest paths."""
    root.mkdir(parents=True, exist_ok=True)
    members = [f"crates/{spec.name}" for spec in specs]
    _write_workspace_manifest(root, members)

    manifests: dict[str, Path] = {}
    crates: list[WorkspaceCrate] = []
    for spec in specs:
        crate_dir = root / "crates" / spec.name
        crate_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = crate_dir / "Cargo.toml"
        _write_crate_manifest(
            manifest_path,
            name=spec.name,
            version=spec.version,
            extra_sections=spec.manifest_extra,
        )
        manifests[spec.name] = manifest_path
        crates.append(
            WorkspaceCrate(
                id=f"{spec.name}-id",
                name=spec.name,
                version=spec.version,
                manifest_path=manifest_path,
                root_path=crate_dir,
                publish=True,
                readme_is_workspace=False,
                dependencies=spec.dependencies,
            )
        )
    workspace = WorkspaceGraph(workspace_root=root, crates=tuple(crates))
    return workspace, manifests


def _make_workspace(tmp_path: Path) -> WorkspaceGraph:
    """Construct a workspace graph with two member crates."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    members = ["crates/alpha", "crates/beta"]
    _write_workspace_manifest(tmp_path, members)
    crates: list[WorkspaceCrate] = []
    for member in members:
        crate_dir = tmp_path / member
        crate_dir.mkdir(parents=True)
        manifest_path = crate_dir / "Cargo.toml"
        manifest_path.write_text(
            f'[package]\nname = "{crate_dir.name}"\nversion = "0.1.0"\n'
        )
        crates.append(
            WorkspaceCrate(
                id=f"{crate_dir.name}-id",
                name=crate_dir.name,
                version="0.1.0",
                manifest_path=manifest_path,
                root_path=crate_dir,
                publish=True,
                readme_is_workspace=False,
                dependencies=(),
            )
        )
    return WorkspaceGraph(workspace_root=tmp_path, crates=tuple(crates))


def _load_version(path: Path, table: tuple[str, ...]) -> str:
    """Return the version string stored at ``table`` within ``path``."""
    document = parse_toml(path.read_text())
    current = document
    for key in table:
        current = current[key]
    return current["version"]


def _make_config(**kwargs: str | tuple[str, ...]) -> config_module.LadingConfig:
    """Construct a configuration instance for tests."""
    bump_config = config_module.BumpConfig(**kwargs)
    return config_module.LadingConfig(bump=bump_config)


def test_run_updates_workspace_and_members(tmp_path: Path) -> None:
    """`bump.run` updates the workspace and member manifest versions."""
    workspace = _make_workspace(tmp_path)
    configuration = _make_config()
    message = bump.run(
        tmp_path, "1.2.3", configuration=configuration, workspace=workspace
    )
    assert message == "Updated version to 1.2.3 in 3 manifest(s)."
    assert _load_version(tmp_path / "Cargo.toml", ("workspace", "package")) == "1.2.3"
    for crate in workspace.crates:
        assert _load_version(crate.manifest_path, ("package",)) == "1.2.3"


def test_run_updates_root_package_section(tmp_path: Path) -> None:
    """The workspace manifest `[package]` section also receives the new version."""
    workspace = _make_workspace(tmp_path)
    manifest_path = tmp_path / "Cargo.toml"
    manifest_path.write_text(
        "[package]\n"
        'name = "workspace"\n'
        'version = "0.1.0"\n\n'
        "[workspace]\n"
        'members = ["crates/alpha", "crates/beta"]\n\n'
        "[workspace.package]\n"
        'version = "0.1.0"\n'
    )
    configuration = _make_config()
    bump.run(tmp_path, "7.8.9", configuration=configuration, workspace=workspace)
    assert _load_version(manifest_path, ("package",)) == "7.8.9"
    assert _load_version(manifest_path, ("workspace", "package")) == "7.8.9"


def test_run_skips_excluded_crates(tmp_path: Path) -> None:
    """Crates listed in `bump.exclude` retain their original version."""
    workspace = _make_workspace(tmp_path)
    excluded = workspace.crates[0]
    configuration = _make_config(exclude=(excluded.name,))
    bump.run(tmp_path, "2.0.0", configuration=configuration, workspace=workspace)
    assert _load_version(tmp_path / "Cargo.toml", ("workspace", "package")) == "2.0.0"
    assert _load_version(excluded.manifest_path, ("package",)) == "0.1.0"
    included = workspace.crates[1]
    assert _load_version(included.manifest_path, ("package",)) == "2.0.0"


def test_run_updates_internal_dependency_versions(tmp_path: Path) -> None:
    """Internal dependency requirements are updated across dependency sections."""
    workspace, manifests = _build_workspace_with_internal_deps(
        tmp_path,
        specs=(
            _CrateSpec(name="alpha"),
            _CrateSpec(
                name="beta",
                manifest_extra="""
                [dependencies]
                alpha = "^0.1.0"

                [dev-dependencies]
                alpha = { version = "~0.1.0", path = "../alpha" }

                [build-dependencies.alpha]
                version = "0.1.0"
                path = "../alpha"
                """,
                dependencies=(
                    WorkspaceDependency(
                        package_id="alpha-id",
                        name="alpha",
                        manifest_name="alpha",
                        kind=None,
                    ),
                    WorkspaceDependency(
                        package_id="alpha-id",
                        name="alpha",
                        manifest_name="alpha",
                        kind="dev",
                    ),
                    WorkspaceDependency(
                        package_id="alpha-id",
                        name="alpha",
                        manifest_name="alpha",
                        kind="build",
                    ),
                ),
            ),
        ),
    )

    configuration = _make_config()
    bump.run(tmp_path, "1.2.3", configuration=configuration, workspace=workspace)

    beta_manifest = manifests["beta"]
    beta_document = parse_toml(beta_manifest.read_text(encoding="utf-8"))
    assert beta_document["dependencies"]["alpha"].value == "^1.2.3"
    dev_entry = beta_document["dev-dependencies"]["alpha"]
    assert dev_entry["version"].value == "~1.2.3"
    assert dev_entry["path"].value == "../alpha"
    build_entry = beta_document["build-dependencies"]["alpha"]
    assert build_entry["version"].value == "1.2.3"
    assert build_entry["path"].value == "../alpha"


def test_run_updates_renamed_internal_dependency_versions(tmp_path: Path) -> None:
    """Aliased workspace dependencies are updated using their manifest name."""
    workspace, manifests = _build_workspace_with_internal_deps(
        tmp_path,
        specs=(
            _CrateSpec(name="alpha"),
            _CrateSpec(
                name="beta",
                manifest_extra="""
                [dependencies]
                alpha-core = { package = "alpha", version = "^0.1.0" }
                """,
                dependencies=(
                    WorkspaceDependency(
                        package_id="alpha-id",
                        name="alpha",
                        manifest_name="alpha-core",
                        kind=None,
                    ),
                ),
            ),
        ),
    )

    configuration = _make_config()
    bump.run(tmp_path, "2.3.4", configuration=configuration, workspace=workspace)

    beta_manifest = manifests["beta"]
    beta_document = parse_toml(beta_manifest.read_text(encoding="utf-8"))
    dependency_entry = beta_document["dependencies"]["alpha-core"]
    assert dependency_entry["version"].value == "^2.3.4"
    assert dependency_entry["package"].value == "alpha"


def test_run_normalises_workspace_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command resolves the workspace root before applying updates."""
    workspace_root = tmp_path / "workspace-root"
    workspace = _make_workspace(workspace_root)
    configuration = _make_config()
    relative = Path("workspace-root")
    monkeypatch.chdir(tmp_path)
    bump.run(relative, "3.4.5", configuration=configuration, workspace=workspace)
    manifest_path = workspace_root / "Cargo.toml"
    assert _load_version(manifest_path, ("workspace", "package")) == "3.4.5"


def test_run_uses_loaded_configuration_and_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`bump.run` loads the configuration and workspace when omitted."""
    workspace = _make_workspace(tmp_path)
    configuration = _make_config()
    monkeypatch.setattr(config_module, "current_configuration", lambda: configuration)
    monkeypatch.setattr("lading.workspace.load_workspace", lambda root: workspace)
    bump.run(tmp_path, "9.9.9")
    assert _load_version(tmp_path / "Cargo.toml", ("workspace", "package")) == "9.9.9"


def test_run_reports_when_versions_already_match(tmp_path: Path) -> None:
    """Return a descriptive message when manifests already match the target."""
    workspace = _make_workspace(tmp_path)
    configuration = _make_config()
    target_version = "0.1.0"
    message = bump.run(
        tmp_path,
        target_version,
        configuration=configuration,
        workspace=workspace,
    )
    assert message == "No manifest changes required; all versions already 0.1.0."


def test_update_crate_manifest_skips_version_bump_for_excluded_crate(
    tmp_path: Path,
) -> None:
    """Excluded crates keep their version while dependency requirements refresh."""
    manifest_path = tmp_path / "Cargo.toml"
    manifest_path.write_text(
        """
        [package]
        name = "beta"
        version = "0.1.0"

        [dependencies]
        alpha = "0.1.0"
        """,
        encoding="utf-8",
    )
    crate = WorkspaceCrate(
        id="beta-id",
        name="beta",
        version="0.1.0",
        manifest_path=manifest_path,
        root_path=manifest_path.parent,
        publish=True,
        readme_is_workspace=False,
        dependencies=(
            WorkspaceDependency(
                package_id="alpha-id",
                name="alpha",
                manifest_name="alpha",
                kind=None,
            ),
        ),
    )

    changed = bump._update_crate_manifest(
        crate,
        {"beta"},
        {"alpha"},
        "1.2.3",
    )

    assert changed is True
    document = parse_toml(manifest_path.read_text(encoding="utf-8"))
    assert document["package"]["version"] == "0.1.0"
    assert document["dependencies"]["alpha"].value == "1.2.3"


def test_update_crate_manifest_updates_version_and_dependencies(tmp_path: Path) -> None:
    """Crate manifests receive the new version and dependency updates."""
    manifest_path = tmp_path / "Cargo.toml"
    manifest_path.write_text(
        """
        [package]
        name = "beta"
        version = "0.1.0"

        [dependencies]
        alpha = "^0.1.0"
        """,
        encoding="utf-8",
    )
    crate = WorkspaceCrate(
        id="beta-id",
        name="beta",
        version="0.1.0",
        manifest_path=manifest_path,
        root_path=manifest_path.parent,
        publish=True,
        readme_is_workspace=False,
        dependencies=(
            WorkspaceDependency(
                package_id="alpha-id",
                name="alpha",
                manifest_name="alpha",
                kind=None,
            ),
        ),
    )

    changed = bump._update_crate_manifest(
        crate,
        set(),
        {"alpha"},
        "1.2.3",
    )

    assert changed is True
    document = parse_toml(manifest_path.read_text(encoding="utf-8"))
    assert document["package"]["version"] == "1.2.3"
    assert document["dependencies"]["alpha"].value == "^1.2.3"


def test_format_result_message_handles_changes() -> None:
    """The formatted result message reflects the number of updated manifests."""
    assert (
        bump._format_result_message(0, "1.2.3")
        == "No manifest changes required; all versions already 1.2.3."
    )
    assert (
        bump._format_result_message(2, "4.5.6")
        == "Updated version to 4.5.6 in 2 manifest(s)."
    )


def test_update_manifest_writes_when_changed(tmp_path: Path) -> None:
    """Applying a new version persists changes to disk."""
    manifest_path = tmp_path / "Cargo.toml"
    manifest_path.write_text('[package]\nname = "demo"\nversion = "0.1.0"\n')
    changed = bump._update_manifest(manifest_path, (("package",),), "1.0.0")
    assert changed is True
    assert _load_version(manifest_path, ("package",)) == "1.0.0"


def test_update_manifest_preserves_inline_comment(tmp_path: Path) -> None:
    """Inline comments survive manifest rewrites."""
    manifest_path = tmp_path / "Cargo.toml"
    manifest_path.write_text(
        '[package]\nversion = "0.1.0"  # keep me\n', encoding="utf-8"
    )
    changed = bump._update_manifest(manifest_path, (("package",),), "1.2.3")
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
    changed = bump._update_manifest(manifest_path, (("package",),), "0.1.0")
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
