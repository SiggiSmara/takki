## Summary

<!-- One or two sentences on what this PR changes and why. -->

## Related issue

<!-- Link to the issue that motivated this work. For non-trivial changes, an issue should exist first; see CONTRIBUTING.md. -->

Fixes #

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Language pack contribution
- [ ] Other (please describe)

## Checklist

- [ ] My change preserves the **audio-first** principle — every user-facing interaction still works without a visual display.
- [ ] My change preserves the **offline-first** principle — no new network calls at runtime.
- [ ] External I/O sits behind a `typing.Protocol` per ADR-019; logic does not call hardware/model APIs directly.
- [ ] New code has unit tests against fakes; hardware/model tests are tagged with the appropriate pytest marker.
- [ ] If this introduces or changes an architectural decision, an ADR is added or updated in `docs/architecture.md`.
- [ ] `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, and `uv run pyright` all pass locally.
- [ ] `CHANGELOG.md` updated under `[Unreleased]` if user-facing.

## Notes for reviewers

<!-- Anything you want the reviewer to focus on, known limitations, or follow-up work tracked elsewhere. -->
