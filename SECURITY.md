# Security Policy

Takki is an offline-first desktop application. It does not communicate over the network at runtime, has no server component, does not collect telemetry, and stores no data outside the user's own machine. See [PRIVACY.md](PRIVACY.md) for the full privacy stance.

Despite the offline design, Takki has security-relevant surfaces worth disclosing responsibly:

- **Runtime dependencies.** `faster-whisper`, `pygame`, `pynput`, `pyttsx3`, `wordfreq`, optional `piper-tts`, optional `llama-cpp-python`.
- **Model files downloaded at first run.** Piper voice models, optionally Whisper models and LLM tier models. Integrity is verified against the publisher's metadata where available.
- **Locally stored data.** SQLite database per installation containing child profile names, progress, voice/display settings.
- **Native code paths.** PyInstaller-bundled Windows executable.

## Reporting a vulnerability

Please report suspected vulnerabilities privately by email to <runningman69@gmail.com>. Include:

- A clear description of the issue
- Reproduction steps if known
- The affected Takki version
- Any suggested mitigation

Please do **not** open a public issue for security vulnerabilities until a fix is available.

## Expected response

This is a hobby project maintained in personal time. The maintainer aims to:

- Acknowledge receipt within 7 days
- Provide an initial assessment within 30 days
- Coordinate disclosure timing with the reporter once a fix is in progress

Credit is given to reporters in release notes unless they request otherwise.

## Out of scope

- Vulnerabilities in upstream dependencies — please report those to the relevant upstream project. Takki tracks dependency advisories via GitHub's Dependabot.
- Issues that require the attacker to already have full access to the user's machine.
