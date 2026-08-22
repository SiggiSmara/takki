import itertools
from dataclasses import dataclass
from enum import Enum, auto

from takki.audio.tts_worker import TTSWorker
from takki.clock import Clock
from takki.display.focus import FocusEvent, FocusGained, FocusLost, FocusSource
from takki.input import KeyEvent
from takki.input.taxonomy import (
    Character,
    Classification,
    KeyBindings,
    RecoveryKey,
    ResumeKey,
    classify,
)

# Placeholder English. ADR-022 moves every user-facing string to per-language
# YAML; no string table exists yet, so these live here until it does.
PAUSED_ANNOUNCEMENT = "Paused. Takki is not the active window."
RESUMED_ANNOUNCEMENT = "Back in Takki."
ALT_TAB_HINT = "Press Alt+Tab to come back to Takki."


@dataclass(frozen=True)
class TypedCharacter:
    char: str


@dataclass(frozen=True)
class RereadPrompt:
    pass


@dataclass(frozen=True)
class RestartWord:
    pass


LessonCommand = TypedCharacter | RereadPrompt | RestartWord


class FocusState(Enum):
    ACTIVE = auto()
    PAUSED = auto()


def _seconds(milliseconds: int) -> float:
    return milliseconds / 1000.0


class FocusModel:
    """ACTIVE/PAUSED FSM and focus-gated dispatch (ADR-028 § C8, concurrency-model.md § The loop)."""

    def __init__(
        self,
        focus: FocusSource,
        speech: TTSWorker,
        clock: Clock,
        bindings: KeyBindings | None = None,
    ) -> None:
        self._focus = focus
        self._speech = speech
        self._clock = clock
        self._bindings = bindings if bindings is not None else KeyBindings()
        self._utterance_ids = itertools.count()
        # ACTIVE is the normal startup state -- the window comes up focused.
        # A window that does not is corrected by the seed event FocusSource
        # emits at construction, which arrives before any key event.
        self.state = FocusState.ACTIVE
        # Named keys currently held, so OS auto-repeat is not read as a new
        # press (ADR-012 § Recovery). Character keys are deliberately absent:
        # whether a held letter counts as repeated attempts is the engine's
        # call (sessions 9-10), not the gate's.
        self._down: set[str] = set()
        self._restart_deadline: float | None = None
        self._restart_fired = False
        self._resume_deadline: float | None = None
        self._request_deadline: float | None = None

    def handle(self, event: KeyEvent | FocusEvent) -> LessonCommand | None:
        if isinstance(event, FocusGained):
            self._on_focus_gained()
            return None
        if isinstance(event, FocusLost):
            self._on_focus_lost()
            return None
        return self._on_key(event)

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
        if self._resume_deadline is not None and now >= self._resume_deadline:
            self._resume_deadline = None
            self._focus.request_foreground()
            self._request_deadline = now + _seconds(self._bindings.resume_request_timeout_ms)
        if self._request_deadline is not None and now >= self._request_deadline:
            # Expiry is the only failure signal: the raise may have been refused
            # or downgraded to a taskbar flash, and request_foreground() cannot
            # say which (ADR-028 § Re-acquire has no synchronous answer).
            self._request_deadline = None
            self._announce(ALT_TAB_HINT)
        return None

    def _on_focus_lost(self) -> None:
        if self.state is FocusState.PAUSED:
            return
        self.state = FocusState.PAUSED
        self._clear_gestures()
        # The prompt in flight is stale the moment the child leaves, and would
        # otherwise hold the worker long enough to delay the pause announcement.
        self._speech.stop()
        self._announce(PAUSED_ANNOUNCEMENT)

    def _on_focus_gained(self) -> None:
        if self.state is FocusState.ACTIVE:
            return
        self.state = FocusState.ACTIVE
        # Clears _request_deadline too: an arriving FocusGained *is* the success
        # signal, whether it came from the held key's request or a manual
        # Alt+Tab -- both resume routes converge here.
        self._clear_gestures()
        # An Alt+Tab hint still being spoken is now false, and would delay the
        # resume announcement behind it.
        self._speech.stop()
        self._announce(RESUMED_ANNOUNCEMENT)

    def _on_key(self, event: KeyEvent) -> LessonCommand | None:
        classification = classify(event, self._bindings, paused=self.state is FocusState.PAUSED)
        if not event.pressed:
            return self._on_release(event, classification)
        if event.name is not None:
            if event.name in self._down:
                return None
            self._down.add(event.name)
        if self.state is FocusState.PAUSED:
            # Focus gating: lesson input is dropped before any lesson logic
            # runs. The resume key is the one exception -- pynput's hook is
            # global, so it is still seen, and it is the way back.
            if isinstance(classification, ResumeKey):
                self._resume_deadline = self._clock.monotonic() + _seconds(
                    self._bindings.resume_hold_ms
                )
            return None
        if isinstance(classification, Character):
            return TypedCharacter(classification.char)
        if isinstance(classification, RecoveryKey):
            return self._on_recovery_press(classification)
        # TalkKey is classified and then dropped: the voice subsystem is Beta
        # (ADR-020), so Alpha has nothing to route it to. Composing, Boundary
        # and System are ignored by the taxonomy itself.
        return None

    def _on_recovery_press(self, key: RecoveryKey) -> LessonCommand | None:
        if key.reread and key.restart:
            self._restart_deadline = self._clock.monotonic() + _seconds(
                self._bindings.restart_hold_ms
            )
            self._restart_fired = False
            return None
        # Two different keys: each fires its own action on press, no hold timing.
        return RereadPrompt() if key.reread else RestartWord()

    def _on_release(self, event: KeyEvent, classification: Classification) -> LessonCommand | None:
        if event.name is not None:
            self._down.discard(event.name)
        if self.state is FocusState.PAUSED:
            if isinstance(classification, ResumeKey):
                self._resume_deadline = None
            return None
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
        # Deadlines only. _down survives on purpose: a key held across the
        # transition keeps auto-repeating, and clearing it here would let the
        # next repeat read as a fresh press and fire an unasked-for restart.
        # A release missed on the secure desktop leaks one entry, which the
        # next release of that key clears -- costing one gesture, not a word.
        self._restart_deadline = None
        self._restart_fired = False
        self._resume_deadline = None
        self._request_deadline = None

    def _announce(self, text: str) -> None:
        self._speech.enqueue_speak(text, next(self._utterance_ids))
