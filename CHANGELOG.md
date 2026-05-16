# Changelog

All notable changes to Takki will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffolding, architecture documentation (ADR-001 through ADR-022), and phased implementation roadmap.
- Contributor and security documentation: `CODE_OF_CONDUCT.md`, `SECURITY.md`, `PRIVACY.md`, issue and pull request templates.
- Tooling baseline: `ruff` for linting and formatting, `pyright` for type checking, `pre-commit` for hook orchestration, `pytest` markers for the tiered test pyramid.
- ADR-020: voice input is push-to-talk only (default Right Ctrl, per-profile configurable).
- ADR-021: voice activity detection via `webrtcvad` for end-of-utterance only.
- ADR-022: YAML across all localisation surfaces (UI strings, encouragement bank, intents, voice catalog).

[Unreleased]: https://github.com/SiggiSmara/takki/commits/main
