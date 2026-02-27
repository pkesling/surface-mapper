# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

## [Unreleased]

### Added
- GitHub CI workflow for lint/test on push and pull requests.
- Contributor guide (`CONTRIBUTING.md`).
- Embedded output metadata for flat PNG renders and 3D GLB exports.
- Dataset attribution embedding for eBird-derived outputs.
- README example gallery with commands and generated outputs.

### Changed
- Default output paths moved to `outputs/` to keep project root clean.
- Geodata lake derivation now uses padded boundary+neighbors extent for consistent framing.
- Packaging metadata expanded in `pyproject.toml` for publication readiness.

### Removed
- `--depth-scale` in favor of `--height-scale` for 3D height control.
- Experimental `--bit-depth` CLI option.

## [0.1.0] - 2026-02-26

### Added
- Initial public-prep release of SurfaceMapper CLI pipeline:
  - Ingest source data into normalized tables.
  - Build surface metrics on H3 cells.
  - Fetch/derive default geodata layers.
  - Render 2D flat outputs.
  - Export and render 3D mesh outputs.
- Built-in presets (`classic`, `neon`) and configurable render workflow.
- Test suite covering core CLI and rendering behavior.
