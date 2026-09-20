# Takki

**A free, open source touch typing tutor for visually impaired children.**

*Takki (Icelandic): a key or mechanical button — the sound of a key being pressed.*

Takki teaches touch typing through audio. All instruction, feedback, and navigation work without any visual reference. The keyboard is the only input device required.

---

## What makes Takki different

- **Audio first.** Every interaction — what to type next, feedback, menus, progress reports — is spoken aloud. No visual display is required at any point.
- **Offline after install.** No internet connection, no account, no ongoing cost.
- **No administrator rights required.** Designed for school and home use where elevated privileges are unavailable.
- **Multilingual out of the box.** Supports ~40 languages. The lesson engine derives everything from language frequency data automatically — no per-language lesson authoring needed.
- **Minimal setup.** The app detects the system language and begins immediately. The ideal experience: install, hand to child, done.

## Status

**Alpha in progress.** The architecture is agreed and documented, and the core lesson engine — persistence, the language layer, audio, keyboard capture, the focus model, key introduction, drills, progression and the session loop — is built and under test. What remains for Alpha is the Windows platform layer and a hands-on validation run.

See [docs/architecture.md](docs/architecture.md) for the design decisions and rationale, and [docs/roadmap.md](docs/roadmap.md) for the phase plan.

## Platform

Windows desktop (v1). Physical keyboard required. The architecture is intentionally portable — see the architecture document for cross-platform readiness notes.

## Where your data lives

Takki keeps everything in one per-user folder, chosen by the operating system's own convention. Nothing is stored anywhere else, and nothing leaves the machine ([PRIVACY.md](PRIVACY.md)).

| Platform | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\Takki\` — usually `C:\Users\<you>\AppData\Local\Takki\` |
| Linux | `~/.local/share/Takki/` |
| macOS | `~/Library/Application Support/Takki/` |

The folder holds `takki.sqlite` — every profile, all typing progress and accuracy history — and, as later versions add them, `takki_config.yaml`, `custom_words.txt`, and downloaded `voices/`. To back a child's progress up, copy `takki.sqlite`. To start over, delete it.

Windows note: this is **Local** app data, not Roaming. The database runs in WAL mode, whose sidecar files do not survive a roaming-profile sync intact — on a managed school network, roaming it would risk corrupting it at every logoff.

One folder that is deliberately *not* this one: extra speech voices download through your browser to `Documents\Takki\voices\`, where you can find them without digging through hidden system folders. That is the only thing that lives there — progress never does.

Paths come from [`platformdirs`](https://pypi.org/project/platformdirs/), so they follow each platform's convention rather than Takki's preference. To see the exact path on your machine:

```
uv run python -c "from takki.data_dir import data_dir; print(data_dir())"
```

## License

[GPL-3.0-or-later](LICENSE) — copyleft, to keep Takki and any derivative free, and to allow bundling the GPL-licensed lexical resources (e.g. childLex, igerman98) the word engine relies on.

## Contributing

Contributions are welcome, especially from teachers, linguists, and developers working in languages other than English. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.
