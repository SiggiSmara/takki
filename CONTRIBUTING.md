# Contributing to Takki

Thank you for your interest in Takki. Contributions are welcome from developers, teachers, linguists, and anyone who wants to help make touch typing accessible to more visually impaired children.

The project is in early stages — the architecture is agreed but implementation has not yet begun. This is a good moment to get involved.

## Ways to contribute

- **Code** — implementing components described in the architecture
- **Testing** — trying the app with visually impaired children and reporting what works and what doesn't
- **Feedback on the architecture** — raising questions or concerns before implementation is locked in

## Before you start

Please open an issue before beginning significant work. This avoids duplicated effort and ensures the approach fits the project's design principles (offline-first, audio-first, no elevated privileges, minimal setup friction).

For small fixes or documentation changes, a pull request is fine without a prior issue.

## Code style and architecture

- Read [docs/architecture.md](docs/architecture.md) before writing any code. The design decisions there are agreed and should be treated as constraints unless you open an issue to revisit one.
- The lesson engine is intentionally language-agnostic. Changes that make it language-specific will not be accepted without strong justification.
- **All external I/O lives behind a `typing.Protocol`.** This applies to TTS, voice input, keyboard capture, sound cues, word sources, the LLM runner, and any future external interface — not only the three Windows-specific platform interfaces. Application logic must depend on the Protocol, not the concrete implementation. See ADR-019.
- **Tests use fakes by default.** Each Protocol ships with a fake implementation in `tests/fakes/`. New code must come with unit tests that run against fakes; integration tests against real implementations are welcome but optional. Hardware- and model-dependent tests are tagged with pytest markers (`audio`, `model`, `windows_only`, `slow`) and excluded from the default `uv run pytest`. See ADR-019.

## Adding or changing an architectural decision

Architectural decisions are recorded as ADRs in [docs/architecture.md](docs/architecture.md). To propose a new one or revise an existing one:

1. Open an issue describing the decision, the alternatives you considered, and the reason for the change.
2. Discussion happens on the issue. Once the direction is agreed, open a pull request that adds or amends the relevant ADR (and the Table of Contents). For new ADRs, use the next available number.
3. The PR is merged by a maintainer once the ADR is clear, internally consistent with other ADRs, and reflects the agreed direction.

Architectural decisions are sticky on purpose. Revisiting an existing ADR requires the same process — please do not silently work around a decision in code.

## Code of Conduct

By participating, you agree to abide by the project's [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
