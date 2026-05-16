# Privacy

Takki is designed for children, and specifically for visually impaired children. Privacy is a first-class architectural concern, not a feature added on top.

## The short version

- Takki runs entirely on your own computer.
- No voice, typing, or progress data is ever sent anywhere.
- No accounts, no telemetry, no analytics, no advertising, no third-party tracking.
- The application does not access the network at runtime, except for one-time downloads of voice and language model files that you explicitly approve.

## What data Takki handles

| Data | Where it lives | Who can see it |
|---|---|---|
| Child profile name | SQLite file on this computer | Anyone with file access to this computer |
| Typing progress and accuracy history | SQLite file on this computer | Same as above |
| Voice/display settings per profile | SQLite file on this computer | Same as above |
| Microphone audio (for voice commands) | Held in memory only during recognition, then discarded | Nobody — not stored, not transmitted |
| Spoken voice command transcriptions | Held in memory only during intent resolution, then discarded | Nobody — not stored, not transmitted |

The SQLite database file is yours. You can copy it, back it up, move it to another computer, or delete it. Its location is documented in the application; on Windows it sits in `%APPDATA%\Takki\`.

## What Takki never does

- Connect to the internet at runtime (after the one-time model setup you approved)
- Send voice recordings or transcriptions to any server
- Upload typing data, accuracy data, or session history anywhere
- Use cloud speech recognition or cloud text-to-speech
- Use cloud LLM services such as OpenAI, Anthropic, or Google APIs
- Show advertising
- Run analytics
- Verify identity, sign in, or require an account

## One-time downloads

At first run, with your explicit confirmation, Takki may download:

- A Piper voice model for your chosen language (tens to hundreds of MB)
- Optionally, a local LLM model if your hardware supports one (1–5 GB)
- A Whisper speech recognition model (if you enable voice control)

These are one-time downloads from the model publishers' hosting (typically Hugging Face). After download, the files are cached on your computer and Takki uses them locally with no further network access.

## Compliance posture

Takki's architecture aligns with:

- **GDPR-K** (EU) — no personal data is collected, processed, or stored outside the user's own device. There is no data controller because there is no data flow off the device.
- **COPPA** (US) — no information is collected from children. The "operator" definition does not apply because there is no online service.

If you deploy Takki in a school or other institutional setting, the responsible party for any local data handling is the institution operating the computer. Takki itself is not a data processor.

## How this stance is enforced

This is a deliberate architectural decision. The relevant decisions in [docs/typing_tutor_architecture.md](docs/typing_tutor_architecture.md):

- ADR-002 (speech recognition is local-only)
- ADR-003 (text-to-speech is local-only)
- ADR-004 (LLM is local-only; cloud LLM is explicitly out of scope)
- ADR-011 (persistence is a local SQLite file with no sync)
- Design principles in section 1

Contributions that introduce network calls at runtime, telemetry, analytics, or cloud service integration will not be accepted.

## Questions

If you have questions about how Takki handles data, or you believe a behaviour does not match what this document describes, please open an issue or email <runningman69@gmail.com>.
