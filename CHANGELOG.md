# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Versioning rule of thumb:**
- `x` (major) — a user must edit existing files to get equivalent output.
  Example: a field is renamed (`stroke_color` → `stroke`), or a default changes
  silently (old diagrams now render differently without any config change).
- `y` (minor) — new capability added; existing files work unchanged.
- `z` (patch) — something was wrong and is now correct; no schema change.

---

## [Unreleased]

## [1.1.0] - 2026-04-08

### Added
- Section band links support six visual styles composed from two shape modes
  (`polygon`, `curve`) and three stroke/fill combinations (fill-only,
  solid-stroke, dashed-stroke). Configured via `shape`, `fill`, `stroke`,
  and `stroke_dasharray` in the theme `links` block.
- New examples under `examples/link/` demonstrating each of the six styles.
- `mmpviz --version` prints the current version number.

### Changed
- Default link style is now stroke-only (`fill: none`). Themes relying on the
  previous implicit gray fill should add `"fill": "gray"` to their `links` block.
- `examples/link/` reorganised into named subfolders; `examples/link_styles/` removed.

## [1.0.0] - 2026-04-07

### Added
- Initial release of mmpviz, based on
  [linkerscope v0.3.1](https://github.com/raulgotor/linkerscope).
- DSL changed from YAML to JSON (`diagram.json`).
- Visual styling separated into a standalone `theme.json`, decoupled from the
  semantic diagram description.
- Initial support of SKILL (Claude Code skill integration).
