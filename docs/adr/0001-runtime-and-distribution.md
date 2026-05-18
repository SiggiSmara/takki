# ADR-001: Runtime and Distribution

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Python 3.11+, distributed as a PyInstaller standalone executable bundle.

### Rationale

Python provides the best combination of:
- No administrator rights required for keyboard/microphone/speaker access
- Rich ecosystem for speech, ML, and audio libraries
- Broad familiarity among open source contributors
- Cross-version stability for long-term maintenance

PyInstaller bundles the Python runtime into the executable, meaning users do not need to install Python separately. This is critical for accessibility — a visually impaired parent should not need to navigate a Python installation process.

### Alternatives Considered

- **Electron/web stack:** Rejected. Heavy, adds complexity with no benefit for this use case. Audio latency concerns.
- **C# / .NET:** Good Windows integration but narrows the contributor pool significantly and is less suited to ML/speech libraries.
- **Requiring Python install:** Rejected. Too much friction for non-technical users.
