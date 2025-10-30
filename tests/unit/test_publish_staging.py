"""Unit tests exercising publish staging utilities."""

from __future__ import annotations

import typing as typ

import pytest

from lading.commands import publish
from tests.unit.conftest import _CrateSpec

if typ.TYPE_CHECKING:
    from pathlib import Path

    from lading import config as config_module
    from lading.workspace import WorkspaceCrate, WorkspaceGraph


def test_normalise_build_directory_defaults_to_tempdir(tmp_path: Path) -> None:
    """Normalisation creates a temporary directory when none is provided."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    build_directory = publish._normalise_build_directory(workspace_root, None)

    assert build_directory.exists()
    assert build_directory.is_absolute()
    assert not build_directory.is_relative_to(workspace_root)


def test_normalise_build_directory_resolves_relative_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Relative build directories are resolved against the current directory."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    monkeypatch.chdir(tmp_path)

    build_directory = publish._normalise_build_directory(workspace_root, "staging")

    expected = (tmp_path / "staging").resolve()
    assert build_directory == expected
    assert build_directory.exists()


def test_normalise_build_directory_rejects_workspace_descendants(
    tmp_path: Path,
) -> None:
    """Normalisation rejects build directories nested under the workspace."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    build_directory = workspace_root / "target"

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish._normalise_build_directory(workspace_root, build_directory)

    assert "cannot reside within the workspace root" in str(excinfo.value)


def test_copy_workspace_tree_mirrors_workspace_contents(tmp_path: Path) -> None:
    """Workspace files are cloned into the staging directory."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    manifest = workspace_root / "Cargo.toml"
    manifest.write_text("[workspace]\n", encoding="utf-8")
    nested_dir = workspace_root / "crates" / "alpha"
    nested_dir.mkdir(parents=True)
    nested_file = nested_dir / "README.md"
    nested_file.write_text("# README\n", encoding="utf-8")

    build_directory = tmp_path / "staging"
    build_directory.mkdir()

    staging_root = publish._copy_workspace_tree(
        workspace_root, build_directory, preserve_symlinks=True
    )

    assert staging_root == build_directory / workspace_root.name
    assert (staging_root / "Cargo.toml").read_text(encoding="utf-8") == "[workspace]\n"
    assert (staging_root / "crates" / "alpha" / "README.md").read_text(
        encoding="utf-8"
    ) == "# README\n"


def test_copy_workspace_tree_replaces_existing_clone(tmp_path: Path) -> None:
    """Existing staging directories are replaced with a fresh copy."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "marker.txt").write_text("fresh", encoding="utf-8")

    build_directory = tmp_path / "staging"
    existing_clone = build_directory / workspace_root.name
    existing_clone.mkdir(parents=True)
    stale_file = existing_clone / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    staging_root = publish._copy_workspace_tree(
        workspace_root, build_directory, preserve_symlinks=True
    )

    assert staging_root == existing_clone
    assert not stale_file.exists()
    assert (staging_root / "marker.txt").read_text(encoding="utf-8") == "fresh"


def test_copy_workspace_tree_rejects_nested_clone(tmp_path: Path) -> None:
    """Copying into a directory under the workspace is prohibited."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish._copy_workspace_tree(
            workspace_root, workspace_root, preserve_symlinks=True
        )

    assert "cannot be nested inside the workspace root" in str(excinfo.value)


def test_copy_workspace_tree_preserves_symlinks(tmp_path: Path) -> None:
    """Workspace symlinks remain symlinks when preservation is enabled."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    target = workspace_root / "data.txt"
    target.write_text("payload", encoding="utf-8")
    link = workspace_root / "alias.txt"
    link.symlink_to(target.name)

    build_directory = tmp_path / "staging"
    build_directory.mkdir()

    staging_root = publish._copy_workspace_tree(
        workspace_root, build_directory, preserve_symlinks=True
    )

    staged_link = staging_root / "alias.txt"
    assert staged_link.is_symlink()
    assert staged_link.resolve(strict=True) == staging_root / "data.txt"
    assert staged_link.read_text(encoding="utf-8") == "payload"


def test_copy_workspace_tree_dereferences_symlinks(tmp_path: Path) -> None:
    """Symlinks become regular files when preservation is disabled."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    target = workspace_root / "data.txt"
    target.write_text("payload", encoding="utf-8")
    link = workspace_root / "alias.txt"
    link.symlink_to(target.name)

    build_directory = tmp_path / "staging"
    build_directory.mkdir()

    staging_root = publish._copy_workspace_tree(
        workspace_root, build_directory, preserve_symlinks=False
    )

    staged_link = staging_root / "alias.txt"
    assert staged_link.is_file()
    assert not staged_link.is_symlink()
    assert staged_link.read_text(encoding="utf-8") == "payload"


def test_stage_workspace_readmes_returns_empty_list_when_unused(
    tmp_path: Path,
) -> None:
    """No work is performed when no crates opt into the workspace README."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    copied = publish._stage_workspace_readmes(
        crates=(), workspace_root=workspace_root, staging_root=staging_root
    )

    assert copied == ()


def test_stage_workspace_readmes_copies_and_sorts_targets(
    tmp_path: Path,
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
) -> None:
    """Workspace README is copied into each opted-in crate in sorted order."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    readme = workspace_root / "README.md"
    readme.write_text("workspace", encoding="utf-8")
    crate_alpha = make_crate(workspace_root, "alpha", _CrateSpec(readme_workspace=True))
    crate_beta = make_crate(workspace_root, "beta", _CrateSpec(readme_workspace=True))
    staging_root = tmp_path / "staging" / "workspace"
    staging_root.mkdir(parents=True)

    copied = publish._stage_workspace_readmes(
        crates=(crate_alpha, crate_beta),
        workspace_root=workspace_root,
        staging_root=staging_root,
    )

    relative = [path.relative_to(staging_root).as_posix() for path in copied]
    assert relative == ["alpha/README.md", "beta/README.md"]
    for path in copied:
        assert path.read_text(encoding="utf-8") == "workspace"


def test_stage_workspace_readmes_requires_workspace_readme(
    tmp_path: Path,
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
) -> None:
    """Crates requesting the workspace README require the source file."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    crate = make_crate(workspace_root, "alpha", _CrateSpec(readme_workspace=True))
    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish._stage_workspace_readmes(
            crates=(crate,), workspace_root=workspace_root, staging_root=staging_root
        )

    assert "Workspace README.md is required" in str(excinfo.value)


def test_stage_workspace_readmes_rejects_external_crates(
    tmp_path: Path,
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
) -> None:
    """Crates outside the workspace cannot receive the workspace README."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    readme = workspace_root / "README.md"
    readme.write_text("workspace", encoding="utf-8")

    external_root = tmp_path / "external"
    crate = make_crate(external_root, "alpha", _CrateSpec(readme_workspace=True))
    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish._stage_workspace_readmes(
            crates=(crate,), workspace_root=workspace_root, staging_root=staging_root
        )

    assert "outside the workspace root" in str(excinfo.value)


def test_prepare_workspace_copies_workspace_readme(
    tmp_path: Path,
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_config: typ.Callable[..., config_module.LadingConfig],
    publish_options: publish.PublishOptions,
) -> None:
    """Staging copies the workspace README into crates that opt in."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    readme = workspace_root / "README.md"
    readme.write_text("Workspace README", encoding="utf-8")
    crate = make_crate(workspace_root, "alpha", _CrateSpec(readme_workspace=True))
    workspace = make_workspace(workspace_root, crate)
    configuration = make_config()
    plan = publish.plan_publication(workspace, configuration)
    preparation = publish.prepare_workspace(plan, workspace, options=publish_options)

    staging_root = preparation.staging_root
    assert staging_root.exists()
    staged_readme = (
        staging_root / crate.root_path.relative_to(workspace_root) / "README.md"
    )
    assert staged_readme.exists()
    assert staged_readme.read_text(encoding="utf-8") == readme.read_text(
        encoding="utf-8"
    )
    assert preparation.copied_readmes == (staged_readme,)


def test_prepare_workspace_requires_workspace_readme(
    tmp_path: Path,
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """Staging fails fast when crates expect the workspace README."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    crate = make_crate(workspace_root, "alpha", _CrateSpec(readme_workspace=True))
    workspace = make_workspace(workspace_root, crate)
    configuration = make_config()
    plan = publish.plan_publication(workspace, configuration)

    with pytest.raises(publish.PublishPreparationError) as excinfo:
        publish.prepare_workspace(
            plan,
            workspace,
            options=publish.PublishOptions(build_directory=tmp_path / "staging"),
        )

    assert "README.md" in str(excinfo.value)


def test_prepare_workspace_registers_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_crate: typ.Callable[[Path, str, _CrateSpec | None], WorkspaceCrate],
    make_workspace: typ.Callable[[Path, WorkspaceCrate], WorkspaceGraph],
    make_config: typ.Callable[..., config_module.LadingConfig],
) -> None:
    """Cleanup-enabled staging registers an atexit handler."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    crate = make_crate(workspace_root, "alpha")
    workspace = make_workspace(workspace_root, crate)
    plan = publish.plan_publication(workspace, make_config())

    build_directory = tmp_path / "staging"
    registered: list[typ.Callable[[], None]] = []

    def capture(callback: typ.Callable[[], None]) -> None:
        registered.append(callback)

    monkeypatch.setattr(publish.atexit, "register", capture)

    options = publish.PublishOptions(build_directory=build_directory, cleanup=True)
    preparation = publish.prepare_workspace(plan, workspace, options=options)

    assert len(registered) == 1
    cleanup = registered[0]
    assert callable(cleanup)
    assert preparation.staging_root.parent == build_directory
    assert build_directory.exists()

    cleanup()
    assert not build_directory.exists()
