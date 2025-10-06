"""Tests for ``lading.config``."""

from __future__ import annotations

import textwrap
import typing as typ

import pytest

from lading import config as config_module

if typ.TYPE_CHECKING:
    from pathlib import Path


def _write_config(tmp_path: Path, body: str) -> Path:
    config_path = tmp_path / config_module.CONFIG_FILENAME
    config_path.write_text(textwrap.dedent(body).lstrip())
    return config_path


def test_load_configuration_parses_values(tmp_path: Path) -> None:
    """Load a representative configuration document."""
    _write_config(
        tmp_path,
        """
        [bump]
        doc_files = ["README.md", "docs/**/*.md"]
        exclude = ["internal"]

        [publish]
        exclude = ["examples"]
        order = ["core"]
        strip_patches = "all"
        """,
    )

    configuration = config_module.load_configuration(tmp_path)

    assert configuration.bump.doc_files == ("README.md", "docs/**/*.md")
    assert configuration.bump.exclude == ("internal",)
    assert configuration.publish.exclude == ("examples",)
    assert configuration.publish.order == ("core",)
    assert configuration.publish.strip_patches == "all"


def test_load_configuration_applies_defaults(tmp_path: Path) -> None:
    """Missing tables fall back to default values."""
    _write_config(tmp_path, "# empty file still constitutes valid TOML")

    configuration = config_module.load_configuration(tmp_path)

    assert configuration.bump.doc_files == ()
    assert configuration.publish.strip_patches == "per-crate"


def test_load_configuration_requires_file(tmp_path: Path) -> None:
    """Raise a descriptive error when ``lading.toml`` is absent."""
    with pytest.raises(config_module.MissingConfigurationError):
        config_module.load_configuration(tmp_path)


def test_invalid_sequence_values_raise(tmp_path: Path) -> None:
    """Reject non-string entries in sequence fields."""
    _write_config(
        tmp_path,
        """
        [bump]
        doc_files = [1]
        """,
    )

    with pytest.raises(config_module.ConfigurationError):
        config_module.load_configuration(tmp_path)


def test_use_configuration_sets_context(tmp_path: Path) -> None:
    """The configuration context manager exposes the active configuration."""
    _write_config(tmp_path, "")
    configuration = config_module.load_configuration(tmp_path)

    with pytest.raises(config_module.ConfigurationNotLoadedError):
        config_module.current_configuration()

    with config_module.use_configuration(configuration):
        assert config_module.current_configuration() is configuration

    with pytest.raises(config_module.ConfigurationNotLoadedError):
        config_module.current_configuration()
