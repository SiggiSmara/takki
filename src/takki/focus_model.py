from dataclasses import dataclass
from enum import Enum, auto

from takki.clock import Clock
from takki.display.focus import FocusEvent, FocusGained, FocusLost
from takki.input.taxonomy import Boundary, Character, KeyBindings, RecoveryKey, System, classify
from takki.input.window_keys import KeyDown, KeyUp, TextTyped, WindowKeyEvent
from takki.speech import Speaker

# Placeholder English. ADR-022 moves every user-facing string to per-language
# YAML; no string table exists yet, so these live here until it does.
# Names the way back, not just the state: Takki's window sees no key while
# another window has focus (alpha-plan #13), so Alt+Tab is the way back.
PAUSED_ANNOUNCEMENT = "Paused. Press Alt+Tab to come back to Takki."
RESUMED_ANNOUNCEMENT = "Back in Takki."


@dataclass(frozen=True)
class TypedCharacter:
    char: str
    # True when the text was not fresh (takki.input.window_keys): an OS
    # auto-repeat of a key that never came up, or the second character of one
    # press. The gate reports the fact and suppresses nothing; what a repeat
    # means for counting is ADR-027 § First-Attempt Counting's call, and the
    # answer there is that it is not an attempt.
    repeat: bool = False


@dataclass(frozen=True)
class RereadPrompt:
    pass


@dataclass(frozen=True)
class RestartWord:
    pass


@dataclass(frozen=True)
class Pressed:
    """A fresh press of a key that is no binding, by its SDL scan code: letters, Shift, a dead key.

    Nothing in a lesson answers one: a lesson answers the text a press typed.
    The alignment does, by the key's cell, since a landing is a physical key
    whatever it types (ADR-033).
    """

    scancode: int


LessonCommand = TypedCharacter | RereadPrompt | RestartWord | Pressed


class FocusState(Enum):
    ACTIVE = auto()
    PAUSED = auto()


def _seconds(milliseconds: int) -> float:
    return milliseconds / 1000.0


class FocusModel:
    """ACTIVE/PAUSED FSM and focus-gated dispatch (ADR-028 § C8, concurrency-model.md § The loop)."""

    def __init__(
        self,
        speech: Speaker,
        clock: Clock,
        bindings: KeyBindings | None = None,
    ) -> None:
        self._speech = speech
        self._clock = clock
        self._bindings = bindings if bindings is not None else KeyBindings()
        # ACTIVE is the normal startup state -- the window comes up focused.
        # A window that does not is corrected by the seed event FocusSource
        # emits at construction, which arrives before any key event.
        self.state = FocusState.ACTIVE
        # The keys held, by SDL scan code. SDL releases every held key just
        # before it reports the focus lost, and a key still held when focus
        # returns is invisible until it is pressed again (alpha-plan #13), so
        # nothing is left down that is not.
        self._down: set[int] = set()
        self._restart_deadline: float | None = None
        self._restart_fired = False

    def handle(self, event: WindowKeyEvent | FocusEvent) -> LessonCommand | None:
        if isinstance(event, FocusGained):
            self._on_focus_gained()
            return None
        if isinstance(event, FocusLost):
            self._on_focus_lost()
            return None
        if isinstance(event, KeyDown):
            return self._on_press(event)
        if isinstance(event, KeyUp):
            return self._on_release(event)
        if isinstance(event, TextTyped):
            return self._on_text(event)
        # KeymapChanged: what Takki says about a layout switch is roadmap § D's.
        return None

    def check_deadlines(self) -> LessonCommand | None:
        now = self._clock.monotonic()
        if (
            self._restart_deadline is not None
            and not self._restart_fired
            and now >= self._restart_deadline
        ):
            # Fires at the threshold with the key still down, so the child gets
            # the confirmation the moment the gesture qualifies (ADR-012).
            self._restart_fired = True
            return RestartWord()
        return None

    def is_down(self, scancode: int) -> bool:
        """Whether a key, by its SDL scan code, is still held."""
        return scancode in self._down

    def _on_focus_lost(self) -> None:
        if self.state is FocusState.PAUSED:
            return
        self.state = FocusState.PAUSED
        self._clear_gestures()
        # The prompt in flight is stale the moment the child leaves; announce()
        # replaces it rather than queueing behind it.
        self._announce(PAUSED_ANNOUNCEMENT)

    def _on_focus_gained(self) -> None:
        if self.state is FocusState.ACTIVE:
            return
        self.state = FocusState.ACTIVE
        self._clear_gestures()
        # A pause announcement still being spoken is now false, and announce()
        # cuts it rather than letting it delay the resume line.
        self._announce(RESUMED_ANNOUNCEMENT)

    def _on_press(self, event: KeyDown) -> LessonCommand | None:
        # Every KEYDOWN is a new press: pygame passes none for an auto-repeat,
        # and SDL posts one only for a key its own state has up. No guard for
        # a key already down, which could only ever drop a key's every later
        # press if the two states disagreed (review of #14b, decided by the
        # developer).
        self._down.add(event.scancode)
        if self.state is FocusState.PAUSED:
            # Focus gating: lesson input is dropped before any lesson logic runs.
            return None
        classification = classify(event, self._bindings)
        if isinstance(classification, RecoveryKey):
            return self._on_recovery_press(classification)
        if isinstance(classification, Boundary | System):
            return Pressed(event.scancode)
        # TalkKey is classified and then dropped: the voice subsystem is Beta
        # (ADR-020), so Alpha has nothing to route it to.
        return None

    def _on_text(self, event: TextTyped) -> LessonCommand | None:
        if self.state is FocusState.PAUSED:
            return None
        classification = classify(event, self._bindings)
        if not isinstance(classification, Character):
            return None
        return TypedCharacter(classification.char, repeat=not event.fresh)

    def _on_recovery_press(self, key: RecoveryKey) -> LessonCommand | None:
        if key.reread and key.restart:
            self._restart_deadline = self._clock.monotonic() + _seconds(
                self._bindings.restart_hold_ms
            )
            self._restart_fired = False
            return None
        # Two different keys: each fires its own action on press, no hold timing.
        return RereadPrompt() if key.reread else RestartWord()

    def _on_release(self, event: KeyUp) -> LessonCommand | None:
        self._down.discard(event.scancode)
        if self.state is FocusState.PAUSED:
            return None
        classification = classify(event, self._bindings)
        if (
            isinstance(classification, RecoveryKey)
            and classification.reread
            and classification.restart
            and self._restart_deadline is not None
        ):
            released_early = not self._restart_fired
            self._restart_deadline = None
            self._restart_fired = False
            if released_early:
                return RereadPrompt()
        return None

    def _clear_gestures(self) -> None:
        self._restart_deadline = None
        self._restart_fired = False

    def _announce(self, text: str) -> None:
        self._speech.announce(text)
