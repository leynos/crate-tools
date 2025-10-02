"""Compat modules exposing legacy script entrypoints."""

# This package intentionally re-exports tools from :mod:`crate_tools`
# so existing imports like ``scripts.bump_version`` continue to work after
# the CLI utilities were reorganised into the library package.
