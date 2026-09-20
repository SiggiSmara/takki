"""Entrypoint — constructs the real implementations in the order § Startup requires.

The loop itself talks to Protocols only (ADR-019); everything platform-shaped
is assembled here, once, and handed to it. Ownership of the startup *sequence*
belongs here rather than to each component (concurrency-model.md § Startup).
"""

import os
import queue
import random
import signal
import sys
from collections.abc import Callable
from types import FrameType

from takki import config
from takki.audio.pygame_cues import PygameMixerCues
from takki.audio.synthetic_letters import SyntheticLetterAudioSource
from takki.audio.tts_worker import TTSWorker
from takki.clock import SleepFrameLimiter, SystemClock
from takki.data_dir import database_path, ensure_parent
from takki.display.focus import PygameFocusSource
from takki.input.pynput_stream import PynputKeyStream
from takki.language.wordfreq_source import WordfreqSource
from takki.persistence import Profile, Store
from takki.persistence.sqlite_store import SqliteStore
from takki.platform import PlatformInterface, select_platform_interface
from takki.platform.layout import Layout, build_de, build_en, build_is
from takki.session import InboundEvent, SessionLoop

# ADR-025's TAKKI_DATA_DIR (not yet implemented) is the stated precedent for
# an env override on top of a platform-detected default. This laptop is
# en-150 on a German QWERTZ layout, so an un-overridden run is `en` wordfreq
# against a German grapheme set rather than the English Stage 0 the Alpha
# done-criterion names -- see alpha-plan carry-forward "Test-laptop locale
# and layout".
_LAYOUT_BUILDERS: dict[str, Callable[[], Layout]] = {"en": build_en, "de": build_de, "is": build_is}


def resolve_language(platform: PlatformInterface) -> str:
    # TAKKI_LANG is a bare primary-subtag code ("en", "de", ...), taken as
    # given -- unlike the platform-detected path, it is not run through
    # primary_subtag(), since it is typed by a developer, not a locale API.
    # An empty value is "no override", matching resolve_layout below.
    return os.environ.get("TAKKI_LANG") or platform.get_system_language()


def resolve_layout(platform: PlatformInterface) -> Layout:
    override = os.environ.get("TAKKI_LAYOUT")
    if not override:
        return platform.get_layout_positions()
    if override not in _LAYOUT_BUILDERS:
        raise ValueError(f"TAKKI_LAYOUT={override!r} is not one of {sorted(_LAYOUT_BUILDERS)}")
    return _LAYOUT_BUILDERS[override]()


def _profile(store: Store, language: str) -> Profile:
    # ADR-013's profile selection is Beta. Alpha runs the first profile it
    # finds and creates one if there is none.
    profiles = store.list_profiles()
    return profiles[0] if profiles else store.create_profile("dev", language)


def main() -> None:
    platform = select_platform_interface()
    layout = resolve_layout(platform)

    inbound: queue.Queue[InboundEvent] = queue.Queue()
    # Display first, then the mixer: the window is the keyboard-focus anchor
    # (ADR-016/ADR-028) and must exist before any key event can be gated
    # against it, and its constructor seeds the focus state onto the queue
    # ahead of everything else. `PygameMixerCues` calls `pygame.mixer.init()`
    # itself, which is why the two need sequencing here at all.
    focus = PygameFocusSource(inbound)
    cues = PygameMixerCues()

    speech = TTSWorker(platform.get_fallback_tts(), inbound)
    speech.start()
    letters = SyntheticLetterAudioSource(speech)

    store = SqliteStore(str(ensure_parent(database_path())))
    profile = _profile(store, resolve_language(platform))

    keys = PynputKeyStream(inbound)
    loop = SessionLoop(
        inbound=inbound,
        layout=layout,
        source=WordfreqSource(),
        store=store,
        profile_id=profile.id,
        clock=SystemClock(),
        frames=SleepFrameLimiter(),
        focus=focus,
        keys=keys,
        speech=speech,
        letters=letters,
        cues=cues,
        rng=random.Random(),
    )

    def _on_signal(signum: int, frame: FrameType | None) -> None:
        # Delivered to the main thread, which is why the core lives there:
        # setting a flag is all a handler does (concurrency-model.md § Shutdown).
        loop.stop()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    loop.start()
    loop.run()
    # Joining the listener is the only place a dead pynput hook becomes
    # visible -- it re-raises a callback exception here. `join()` is not on the
    # KeyEventStream Protocol, so the wiring holds the concrete stream to do it
    # (concurrency-model.md § Shutdown). `stop()` already happened in
    # SessionLoop.shutdown().
    keys.join(config.WORKER_JOIN_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
