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
- Platform-specific code must live behind the three clean interfaces described in the architecture (language detection, home row derivation, fallback TTS). Do not call platform APIs directly from application logic.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
