from pathlib import Path

import pytest
import tomlkit

from crate_tools.bump_version import (
    _update_dependency_version,
    _update_markdown_versions,
)
from scripts.bump_version import replace_fences, replace_version_in_toml


@pytest.mark.parametrize(
    "section",
    ["dependencies", "dev-dependencies", "build-dependencies"],
)
@pytest.mark.parametrize(
    "body, expected, extra",
    [
        ('foo = "^0.1"', 'foo = "^1.2.3"', None),
        (
            'foo = { version = "~0.1", features = ["a"] }',
            'version = "~1.2.3"',
            'features = ["a"]',
        ),
    ],
)
def test_updates_dependency_version(
    section: str, body: str, expected: str, extra: str | None
) -> None:
    doc = tomlkit.parse(f"[{section}]\n{body}")
    _update_dependency_version(doc, "foo", "1.2.3")
    dumped = tomlkit.dumps(doc)
    assert expected in dumped
    if extra:
        assert extra in dumped


def test_preserves_trailing_comment_on_string_dependency() -> None:
    doc = tomlkit.parse('[dependencies]\nfoo = "^0.1"  # pinned for CI\n')
    _update_dependency_version(doc, "foo", "1.2.3")
    dumped = tomlkit.dumps(doc)
    assert "# pinned for CI" in dumped, "must preserve trailing comment on value node"


def test_preserves_quote_style_on_string_dependency() -> None:
    doc = tomlkit.parse("[dependencies]\nfoo = '0.1'  # single quoted\n")
    _update_dependency_version(doc, "foo", "1.2.3")
    dumped = tomlkit.dumps(doc)
    assert "foo = '1.2.3'" in dumped, (
        f"expected single quotes preserved, got:\n{dumped}"
    )


def test_missing_dependency_no_change() -> None:
    snippet = '[dependencies]\nbar = "0.1"'
    doc = tomlkit.parse(snippet)
    _update_dependency_version(doc, "foo", "1.2.3")
    assert tomlkit.dumps(doc).strip() == snippet, (
        "should be a no-op when dependency is absent"
    )


def test_workspace_dependency_no_version_written() -> None:
    doc = tomlkit.parse("[dependencies]\nfoo = { workspace = true }\n")
    _update_dependency_version(doc, "foo", "1.2.3")
    deps = doc["dependencies"]["foo"]
    assert "version" not in deps, "must not add version when workspace is true"


@pytest.mark.parametrize(
    "md_text, should_change, description",
    [
        (
            """pre
```toml
[dependencies]
ortho_config = \"0\"
```
post
""",
            True,
            "must update TOML fences",
        ),
        (
            """pre
```bash
echo hi
```
post
""",
            False,
            "must leave non-TOML fences unchanged",
        ),
    ],
)
def test_update_markdown_versions_behavior(
    tmp_path: Path, md_text: str, should_change: bool, description: str
) -> None:
    for rel in ("README.md", "docs/users-guide.md"):
        md_path = tmp_path / rel
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_text)
        _update_markdown_versions(md_path, "1")
        updated = md_path.read_text()
        if should_change:
            assert 'ortho_config = "1"' in updated, description
        else:
            assert updated == md_text, description


def test_update_markdown_preserves_trailing_newline(tmp_path: Path) -> None:
    md_text = """```toml
[dependencies]
ortho_config = { version = \"0.5.0-beta1\", features = [\"json5\", \"yaml\"] }
# Enabling these features expands file formats; precedence stays: defaults < file < env < CLI.
```
"""
    md_path = tmp_path / "README.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text)

    _update_markdown_versions(md_path, "0.5.0")

    updated_lines = md_path.read_text().splitlines()
    assert 'version = "0.5.0"' in "\n".join(updated_lines), (
        "must bump version inside TOML fence"
    )
    assert updated_lines[-2] == (
        "# Enabling these features expands file formats; precedence stays: "
        "defaults < file < env < CLI."
    )
    assert updated_lines[-1] == "```"


@pytest.mark.parametrize(
    "snippet, expected_suffix",
    [
        ('[dependencies]\northo_config = "0"\n', "\n"),
        ('[dependencies]\northo_config = "0"\r\n', "\r\n"),
        ('[dependencies]\northo_config = "0"\n\n', "\n\n"),
        ('[dependencies]\northo_config = "0"\r\n\r\n', "\r\n\r\n"),
        ('[dependencies]\northo_config = "0"', ""),
    ],
)
def test_replace_version_in_toml_preserves_suffix(
    snippet: str, expected_suffix: str
) -> None:
    updated = replace_version_in_toml(snippet, "1")
    base = updated.rstrip("\r\n")
    actual_suffix = updated[len(base) :]
    assert actual_suffix == expected_suffix
    assert 'ortho_config = "1"' in updated


@pytest.mark.parametrize(
    "snippet",
    [
        '[dependencies]\nfoo = "0"\n',
        '[dependencies]\nfoo = "0"\r\n',
        '[dependencies]\nfoo = "0"\n\n',
        '[dev-dependencies]\nfoo = "0"',
        '[build-dependencies]\nfoo = "0"\r\n',
    ],
)
def test_replace_version_in_toml_no_dependency_returns_input(snippet: str) -> None:
    assert replace_version_in_toml(snippet, "1") == snippet


def test_replace_fences_preserves_indentation() -> None:
    md_text = """1. item

    ```toml
    [dependencies]
    foo = "0"
    ```
"""
    replaced = replace_fences(md_text, "toml", lambda body: body.replace("0", "1"))
    expected = """1. item

    ```toml
    [dependencies]
    foo = "1"
    ```
"""
    assert replaced == expected
