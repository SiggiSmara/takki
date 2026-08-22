from dataclasses import dataclass
from typing import Protocol

import pygame

# Private module, but the only route to SDL_RaiseWindow from pygame: there is
# no public window-raise API. A pygame upgrade that moves or drops it breaks
# this import loudly rather than degrading focus silently.
import pygame._sdl2.video as sdl2_video

from takki import config


@dataclass(frozen=True)
class FocusGained:
    pass


@dataclass(frozen=True)
class FocusLost:
    pass


FocusEvent = FocusGained | FocusLost


class EventSink(Protocol):
    # Structural put(), not queue.Queue[FocusEvent] -- same convention as
    # takki.input.EventSink and takki.audio.tts_worker.EventSink: session 11
    # passes the core's single inbound queue, which carries every event type,
    # and Queue's parameter is invariant.
    def put(self, item: FocusEvent, /) -> None: ...


class FocusSource(Protocol):
    def poll(self) -> None: ...

    def request_foreground(self) -> None: ...

    def close(self) -> None: ...


class PygameFocusSource:
    """Always-on SDL window, the keyboard-focus anchor (ADR-016/ADR-028). Blank surface only."""

    def __init__(self, outbound: EventSink) -> None:
        pygame.display.init()
        pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        pygame.display.set_caption(config.WINDOW_TITLE)
        self._outbound = outbound
        self._focused = pygame.key.get_focused()
        # Seed the initial state. The FSM downstream (session 6b) has no way to
        # read focus -- FocusSource deliberately offers no query, since a raise
        # has no synchronous answer -- and poll() below is edge-triggered, so a
        # window that comes up unfocused would otherwise never produce an event
        # and leave the FSM wrongly ACTIVE for the whole run.
        self._outbound.put(FocusGained() if self._focused else FocusLost())

    def poll(self) -> None:
        # Type-filtered: an unfiltered get() drains the whole SDL queue, which
        # would swallow QUIT before the core loop (session 11) ever sees it.
        delivered = False
        for ev in pygame.event.get([pygame.WINDOWFOCUSGAINED, pygame.WINDOWFOCUSLOST]):
            delivered = True
            self._set_focused(ev.type == pygame.WINDOWFOCUSGAINED)

        # Backup poll (ADR-028 § Focus): a secure-desktop transition may not
        # deliver a WINDOWFOCUSGAINED/LOST event, so re-read SDL's own tracked
        # focus state -- a missed event still surfaces on the next tick.
        #
        # Only when no event arrived this tick. An event is the leading edge of
        # a transition and get_focused() may not reflect it yet, so running both
        # would let a stale read immediately cancel an event we just handled.
        if not delivered:
            self._set_focused(pygame.key.get_focused())

    def _set_focused(self, focused: bool) -> None:
        # Edge-triggered. Windows re-delivers WINDOWFOCUSGAINED, and the backup
        # poll re-reads the same state every tick; 6b's FSM gets transitions,
        # not repeats.
        if focused == self._focused:
            return
        self._focused = focused
        self._outbound.put(FocusGained() if focused else FocusLost())

    def request_foreground(self) -> None:
        # Fire-and-forget by necessity: SDL_RaiseWindow is asynchronous, so no
        # synchronous answer exists -- get_focused() here would still read the
        # pre-call state and report failure even when the raise succeeds. The
        # Windows foreground-activation lock may also downgrade it to a taskbar
        # flash (ADR-028 § Resume). Success is observed as a FocusGained event
        # arriving before 6b's deadline, not as a return value.
        sdl2_video.Window.from_display_module().focus()

    def close(self) -> None:
        pygame.display.quit()
