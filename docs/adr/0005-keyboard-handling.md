# ADR-005: Keyboard Handling

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Use `pynput` for key capture. Rely entirely on Windows to report the correct character for the active keyboard layout. No custom layout definitions maintained by the app.

### Rationale

Windows handles keyboard layout translation transparently. When a user presses a key, `pynput` reports the already-translated character — so on a German QWERTZ keyboard, the key in the Z position reports `y`, and the `ü` key reports `ü`. The app never needs to know which physical key was pressed, only which character was produced.

This means:
- No layout definition files to maintain
- No layout detection logic beyond reading the Windows locale
- Automatic correct behaviour for all QWERTY, QWERTZ, AZERTY, and national variant layouts
- Dead keys and AltGr combinations are handled by Windows before the app sees them

`pynput` is chosen over the `keyboard` library because it does not require elevated privileges on Windows for standard key capture.

The push-to-talk key (ADR-020) is captured via the same `pynput` pipeline as any other key; the lesson engine consumes character events and ignores the talk key, while the voice subsystem subscribes to talk-key events and ignores character keys.

### Alternatives Considered

- **Custom layout definition files (JSON):** Rejected. Unnecessary duplication of information Windows already has. Maintenance burden. Risk of mismatch between app definition and actual system layout.
- **`keyboard` library:** Viable alternative but requires more careful privilege handling. `pynput` is cleaner for this use case.
