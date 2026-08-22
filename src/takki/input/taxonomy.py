from dataclasses import dataclass

from takki import config
from takki.input import KeyEvent


@dataclass(frozen=True)
class KeyBindings:
    """Compiled defaults (ADR-025 tier 1); the yaml and per-profile tiers construct this with overrides."""

    talk: str = config.TALK_KEY
    reread: str = config.REREAD_KEY
    restart: str = config.RESTART_KEY
    resume: str = config.RESUME_KEY
    restart_hold_ms: int = config.RESTART_HOLD_MS
    resume_hold_ms: int = config.RESUME_HOLD_MS
    resume_request_timeout_ms: int = config.RESUME_REQUEST_TIMEOUT_MS


@dataclass(frozen=True)
class TalkKey:
    pass


@dataclass(frozen=True)
class RecoveryKey:
    # Which action(s) this key is bound to, not which one fires: with both true
    # (the shared-key default) the caller runs the tap/hold gesture; with one
    # true the key fires that action on press and no hold timing runs at all
    # (ADR-012 § Recovery).
    reread: bool
    restart: bool


@dataclass(frozen=True)
class ResumeKey:
    pass


@dataclass(frozen=True)
class Character:
    # ADR-028's Expected and Wrong rows merged. Splitting them needs the current
    # prompt, which lives in the lesson engine (sessions 7-10) -- so this class
    # carries the character and nothing else, and the engine compares it.
    char: str


@dataclass(frozen=True)
class Composing:
    pass


@dataclass(frozen=True)
class Boundary:
    pass


@dataclass(frozen=True)
class System:
    pass


Classification = TalkKey | RecoveryKey | ResumeKey | Character | Composing | Boundary | System

# ADR-028's Boundary row. Backspace sits here and nowhere else: ADR-012 disables
# it outright, so there is no buffer or undo path for it to reach.
BOUNDARY_KEYS = frozenset({"backspace", "tab", "delete", "enter"})


def classify(event: KeyEvent, bindings: KeyBindings, *, paused: bool) -> Classification:
    """ADR-028 § C8's keypress taxonomy, as a pure function of the event, the bindings and the state."""
    # KeyEvent.name is set only for pynput Key.* members and char only for
    # KeyCode (session 5's translate()), so name-vs-char is the Key/KeyCode
    # split. Bindings are Key.* names per ADR-025 and so are matched on name.
    if event.name is None:
        if event.char is None or not event.char.isprintable():
            return Composing()
        return Character(event.char)
    if paused and event.name == bindings.resume:
        return ResumeKey()
    if event.name == bindings.talk:
        return TalkKey()
    if event.name in (bindings.reread, bindings.restart):
        return RecoveryKey(
            reread=event.name == bindings.reread,
            restart=event.name == bindings.restart,
        )
    if event.name in BOUNDARY_KEYS:
        return Boundary()
    # Everything left is System, which includes Key.space: the space bar is
    # never introduced (ADR-023 § "The space bar is likewise never introduced"),
    # so it has no lesson meaning to classify.
    return System()
