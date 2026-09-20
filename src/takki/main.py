"""Entrypoint — constructs the real implementations in the order § Startup requires.

The loop itself talks to Protocols only (ADR-019); everything platform-shaped
is assembled here, once, and handed to it. Ownership of the startup *sequence*
belongs here rather than to each component (concurrency-model.md § Startup).
"""

import queue
import random
import signal
import sys
from pathlib import Path
from types import FrameType

from takki import config
from takki.audio.pygame_cues import PygameMixerCues
from takki.audio.synthetic_letters import SyntheticLetterAudioSource
from takki.audio.tts_worker import TTSWorker
from takki.clock import SleepFrameLimiter, SystemClock
from takki.display.focus import PygameFocusSource
from takki.input.pynput_stream import PynputKeyStream
from takki.language.wordfreq_source import WordfreqSource
from takki.persistence import Profile, Store
from takki.persistence.sqlite_store import SqliteStore
from takki.platform import select_platform_interface
from takki.session import InboundEvent, SessionLoop

DB_NAME = "takki.sqlite"


def _database_path() -> Path:
    directory = Path.home() / "Documents" / "Takki"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / DB_NAME


def _profile(store: Store, language: str) -> Profile:
    # ADR-013's profile selection is Beta. Alpha runs the first profile it
    # finds and creates one if there is none.
    profiles = store.list_profiles()
    return profiles[0] if profiles else store.create_profile("dev", language)


def main() -> None:
    platform = select_platform_interface()
    layout = platform.get_layout_positions()

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

    store = SqliteStore(str(_database_path()))
    profile = _profile(store, platform.get_system_language())

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
