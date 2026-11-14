from dataclasses import dataclass

from takki import config
from takki.input.window_keys import KeyDown, KeyUp, TextTyped


@dataclass(frozen=True)
class KeyBindings:
    """Compiled defaults (ADR-025 tier 1); the yaml and per-profile tiers construct this with overrides."""

    # SDL scan codes, as config.py's.
    talk: int = config.TALK_KEY
    reread: int = config.REREAD_KEY
    restart: int = config.RESTART_KEY
    restart_hold_ms: int = config.RESTART_HOLD_MS


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
class Character:
    # ADR-028's Expected and Wrong rows merged. Splitting them needs the current
    # prompt, which lives in the lesson engine (sessions 7-10) -- so this class
    # carries the character and nothing else, and the engine compares it.
    #
    # Always lower case: `classify()` folds it, so case never reaches the
    # lesson engine at all (ADR-027 § Case is folded at the boundary).
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


Classification = TalkKey | RecoveryKey | Character | Composing | Boundary | System

# ADR-028's Boundary row, as SDL scan codes: Backspace, Tab, Delete, Enter and
# the keypad's Enter. Backspace sits here and nowhere else: ADR-012 disables
# it outright, so there is no buffer or undo path for it to reach.
BOUNDARY_KEYS = frozenset({42, 43, 76, 40, 88})
SPACE = 44


def classify(event: KeyDown | KeyUp | TextTyped, bindings: KeyBindings) -> Classification:
    """ADR-028 § C8's keypress taxonomy, as a pure function of the event and the bindings."""
    if isinstance(event, TextTyped):
        # The space bar types `' '` but is System by its key: it is never
        # introduced (ADR-023 § "The space bar is likewise never introduced"),
        # so it has no lesson meaning to classify.
        if event.scancode == SPACE:
            return System()
        if not event.text.isprintable():
            return Composing()
        # Case is folded here, once, and never reaches the lesson engine
        # (ADR-027 § Case is folded at the boundary). Takki teaches letters,
        # not the keyboard: Shift and Caps Lock are out of scope by ADR-005,
        # so an upper-case answer is the right letter typed on a keyboard in
        # a state the child cannot see. A blind child has no Caps Lock LED,
        # and rejecting `F` for `f` in silence would be unexplainable.
        #
        # `.lower()`, never `.casefold()`: casefold maps `ß` to `ss`, two
        # characters, which would make the German curriculum untypeable.
        # `.lower()` is single-character for every letter in every alphabet
        # Takki teaches, `ẞ` included.
        return Character(event.text.lower())
    if event.scancode == bindings.talk:
        return TalkKey()
    if event.scancode in (bindings.reread, bindings.restart):
        return RecoveryKey(
            reread=event.scancode == bindings.reread,
            restart=event.scancode == bindings.restart,
        )
    if event.scancode in BOUNDARY_KEYS:
        return Boundary()
    # Every other key's press and release, a letter's included: they say only
    # which key it was. What a press typed, if anything, arrives as its own
    # TextTyped. A press that types nothing (a dead key arming, Shift) is
    # ADR-028's Composing, and nothing in a lesson answers it.
    return System()
