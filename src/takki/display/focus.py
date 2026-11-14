from dataclasses import dataclass
from typing import Protocol

import pygame

from takki import config
from takki.events import Quit
from takki.input.window_keys import WindowKeyEvent, WindowKeyReader


@dataclass(frozen=True)
class FocusGained:
    pass


@dataclass(frozen=True)
class FocusLost:
    pass


FocusEvent = FocusGained | FocusLost


class EventSink(Protocol):
    # Structural put(), not queue.Queue[FocusEvent] -- same convention as
    # takki.audio.tts_worker.EventSink: session 11 passes the core's single
    # inbound queue, which carries every event type, and Queue's parameter is
    # invariant.
    def put(self, item: FocusEvent | WindowKeyEvent | Quit, /) -> None: ...


class FocusSource(Protocol):
    """The window: its focus, its keys and its close button, from one drain (ADR-028 § C8)."""

    def poll(self) -> None: ...

    def close(self) -> None: ...


class PygameFocusSource:
    """Always-on SDL window, the keyboard-focus anchor (ADR-016/ADR-028). Blank surface only."""

    def __init__(self, outbound: EventSink) -> None:
        pygame.display.init()
        pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        pygame.display.set_caption(config.WINDOW_TITLE)
        self._outbound = outbound
        self._keys = WindowKeyReader()
        self._focused = pygame.key.get_focused()
        # Seed the initial state. The FSM downstream (session 6b) has no way to
        # read focus -- FocusSource deliberately offers no query -- and poll()
        # below is edge-triggered, so a
        # window that comes up unfocused would otherwise never produce an event
        # and leave the FSM wrongly ACTIVE for the whole run.
        self._outbound.put(FocusGained() if self._focused else FocusLost())

    def poll(self) -> None:
        # Unfiltered: takes every queued event in order, hands each key event
        # to the reader and acts on each focus and QUIT event, in the order
        # they came, and drops every other type. Nothing else reads this queue,
        # so anything left on it stays there. A type-filtered get() let mouse
        # motion and key events pile up to SDL's 65,535-event cap, after which
        # SDL refuses QUIT and the close button stops working (alpha-plan #12c
        # (3), windows-validation E10). The order is what clears a held key's
        # down-state: SDL posts its KEYUP just before WINDOWFOCUSLOST (#13).
        delivered = False
        for ev in pygame.event.get():
            key = self._keys.read(ev)
            if key is not None:
                self._outbound.put(key)
                continue
            if ev.type not in (pygame.WINDOWFOCUSGAINED, pygame.WINDOWFOCUSLOST, pygame.QUIT):
                continue
            if ev.type == pygame.QUIT:
                # This pump is the only thing that sees QUIT, so it is the only
                # thing that can normalise it onto the core's one inbound
                # stream (concurrency-model.md § The loop). Session 6a filtered
                # it out of this get() precisely so it would still be there for
                # session 11 to claim.
                self._outbound.put(Quit())
                # Counts as an event arriving, so the backup poll below is
                # skipped this tick: a closing window can already read as
                # unfocused, and the FocusLost that would synthesise reaches
                # the core behind the Quit and announces a pause on the way out.
                delivered = True
                continue
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

    def close(self) -> None:
        pygame.display.quit()
