"""Tests for publish_workspace_dependencies helpers."""

from __future__ import annotations

import typing as typ

import pytest

from crate_tools import publish_workspace_dependencies as dependencies

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    """Create a temporary workspace layout for dependency rewrites."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "crates").mkdir()
    return workspace


def _write_rstest_manifest(crate_dir: Path) -> None:
    manifest = crate_dir / "Cargo.toml"
    manifest.write_text(
        "\n".join(
            (
                "[package]",
                'name = "rstest-bdd"',
                'version = "0.0.1"',
                "",
                "[dependencies]",
                'rstest-bdd-patterns = { path = "../rstest-bdd-patterns" }',
                "",
                "[dev-dependencies]",
                'rstest-bdd-macros = { path = "../rstest-bdd-macros" }',
            )
        ),
        encoding="utf-8",
    )


class TestApplyWorkspaceReplacements:
    """Unit and behavioural coverage for dependency replacement workflows."""

    def test_skips_unknown_crates(
        self,
        workspace_root: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Ignore crates without replacement configuration."""
        crate_dir = workspace_root / "crates" / "rstest-bdd"
        crate_dir.mkdir()
        (crate_dir / "Cargo.toml").write_text("", encoding="utf-8")

        captured: list[tuple[str, Path, str, bool]] = []

        def fake_apply(
            crate: str,
            manifest: Path,
            version: str,
            *,
            include_local_path: bool,
        ) -> None:
            captured.append((crate, manifest, version, include_local_path))

        monkeypatch.setattr(dependencies, "apply_replacements", fake_apply)

        with caplog.at_level("WARNING"):
            dependencies.apply_workspace_replacements(
                workspace_root,
                "1.2.3",
                include_local_path=False,
                crates=("rstest-bdd", "unknown-crate"),
            )

        expected_manifest = crate_dir / "Cargo.toml"
        assert captured == [("rstest-bdd", expected_manifest, "1.2.3", False)]
        assert not any(crate == "unknown-crate" for crate, *_ in captured)
        assert "Skipping crates without replacement entries" in caplog.text
        assert "unknown-crate" in caplog.text

    def test_updates_known_crates_when_unknown_requested(
        self,
        workspace_root: Path,
    ) -> None:
        """Behavioural test covering the manifest rewrite flow."""
        crate_dir = workspace_root / "crates" / "rstest-bdd"
        crate_dir.mkdir()
        _write_rstest_manifest(crate_dir)

        dependencies.apply_workspace_replacements(
            workspace_root,
            "2.0.0",
            include_local_path=False,
            crates=("rstest-bdd", "unknown-crate"),
        )

        manifest_text = (crate_dir / "Cargo.toml").read_text(encoding="utf-8")
        assert manifest_text.count('version = "2.0.0"') == 2
        assert "rstest-bdd-patterns" in manifest_text
        # Unknown crates are ignored entirely when replacements are missing.
        assert "unknown-crate = " not in manifest_text
