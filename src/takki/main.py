"""Entrypoint — constructs the real implementations in the order § Startup requires.

The loop itself talks to Protocols only (ADR-019); everything platform-shaped
is assembled here, once, and handed to it. Ownership of the startup *sequence*
belongs here rather than to each component (concurrency-model.md § Startup).
"""

import queue
import random
import signal
import sys
from collections.abc import Callable
from types import FrameType

from takki import config
from takki.audio.pygame_cues import PygameMixerCues
from takki.audio.synthetic_letters import SyntheticLetterAudioSource
from takki.audio.tts import SpeechOutputError
from takki.audio.tts_worker import TTSWorker
from takki.clock import SleepFrameLimiter, SystemClock
from takki.data_dir import database_path, ensure_parent
from takki.display.focus import PygameFocusSource
from takki.input.pynput_stream import PynputKeyStream
from takki.language.wordfreq_source import WordfreqSource
from takki.persistence import Profile, Store
from takki.persistence.sqlite_store import SqliteStore
from takki.platform import PlatformInterface, select_platform_interface
from takki.platform.layout import Layout, build_de, build_en, build_is, describe_mismatch
from takki.session import InboundEvent, SessionLoop

# The curriculum languages Alpha can teach, and the keyboard each one expects.
# Not a config surface: adding a language means adding a layout table, so the
# dictionary and the ADR-009 language set grow together.
_EXPECTED_LAYOUTS: dict[str, Callable[[], Layout]] = {
    "en": build_en,
    "de": build_de,
    "is": build_is,
}

EXIT_LAYOUT_MISMATCH = 2
EXIT_NO_VOICE = 3
EXIT_NO_AUDIO = 4


def resolve_language(platform: PlatformInterface) -> str:
    """The configured language (ADR-025 tier 1), falling back to the system locale."""
    # config.LANGUAGE is the parent-facing knob until the takki_config.yaml
    # tier exists; None means "whatever Windows says", which is ADR-013's
    # locale detection and the right default for a single-language machine.
    return config.LANGUAGE or platform.get_system_language()


def verify_layout(language: str, layout: Layout) -> str | None:
    """None when the machine's keyboard can teach `language`; else why it cannot.

    ADR-006 makes Windows authoritative for the layout, so this does not
    substitute a layout of its own -- it refuses to teach the wrong
    curriculum on the keyboard the child actually has. The case it exists for
    is the ordinary one of a machine with more than one layout installed
    (ADR-025 § Language and layout must agree): this laptop carries German,
    US and Icelandic, and with German active an `en` curriculum would drill
    `y` and `z` at each other's positions and put `ä ö ü ß` in a 30-grapheme
    milestone denominator, silently.
    """
    expected = _EXPECTED_LAYOUTS.get(language)
    if expected is None:
        return (
            f"no layout table for language {language!r}; Alpha teaches {sorted(_EXPECTED_LAYOUTS)}"
        )
    return describe_mismatch(expected(), layout)


def _profile(store: Store, language: str) -> Profile:
    # ADR-013's profile selection is Beta. Alpha runs the first profile it
    # finds and creates one if there is none.
    profiles = store.list_profiles()
    return profiles[0] if profiles else store.create_profile("dev", language)


def main() -> int:
    platform = select_platform_interface()
    language = resolve_language(platform)
    layout = platform.get_layout_positions()

    # Before anything is constructed: a mismatch here means every keystroke
    # for the rest of the run would be scored against the wrong keyboard, and
    # nothing later in startup can detect it. Alpha reports and stops rather
    # than degrading (roadmap § D "Language and layout can disagree"); the
    # graceful in-app resolution -- offer the right layout, or switch
    # curriculum -- is Beta's, with onboarding (ADR-013).
    mismatch = verify_layout(language, layout)
    if mismatch is not None:
        print(f"Takki cannot start: {mismatch}.", file=sys.stderr)
        print(
            "Set the active Windows keyboard layout to match the lesson language "
            "(Win+Space switches between installed layouts), then start Takki again.",
            file=sys.stderr,
        )
        return EXIT_LAYOUT_MISMATCH

    # The second startup precondition, and the same shape as the first: a
    # curriculum Takki cannot pronounce is as unusable as one it cannot type.
    # Alpha's whole loop is "hear a letter, type it" (ADR-012), so a wrong
    # voice is not degraded audio -- it is a prompt the child cannot resolve
    # to a letter, which is the A1 failure by another route. Stop rather than
    # fall back to whatever the system default happens to be (ADR-003
    # § SAPI fallback voice selection).
    voice = platform.find_voice(language)
    if voice is None:
        print(
            f"Takki cannot start: no text-to-speech voice is installed for {language!r}.",
            file=sys.stderr,
        )
        print(
            "Add one in Windows Settings > Time & language > Speech > Manage voices, "
            "then start Takki again.",
            file=sys.stderr,
        )
        return EXIT_NO_VOICE

    inbound: queue.Queue[InboundEvent] = queue.Queue()
    # Display first, then the mixer: the window is the keyboard-focus anchor
    # (ADR-016/ADR-028) and must exist before any key event can be gated
    # against it, and its constructor seeds the focus state onto the queue
    # ahead of everything else. `PygameMixerCues` calls `pygame.mixer.init()`
    # itself, which is why the two need sequencing here at all.
    focus = PygameFocusSource(inbound)
    cues = PygameMixerCues()

    # The voice verified above is applied here, and `get_fallback_tts` hands
    # back a factory rather than an engine -- the worker builds it on its own
    # thread, which is the only thread that can then drive it
    # (concurrency-model.md § The engine belongs to the thread that creates it).
    # The third precondition: a voice that exists but cannot sound. find_voice()
    # reads the registry and cannot see the output device, so the engine proves
    # it by speaking as it is built (ADR-019 § Headless audio/video). Stop, as
    # for the other two -- an audio-first app with no audio has nothing to offer,
    # and nothing to say it with, so the reason goes to stderr.
    speech = TTSWorker(platform.get_fallback_tts(voice), inbound)
    try:
        speech.start()
    except SpeechOutputError as error:
        print(f"Takki cannot start: {error}.", file=sys.stderr)
        print(
            "Check that speakers or headphones are connected and selected as the "
            "Windows sound output, then start Takki again.",
            file=sys.stderr,
        )
        return EXIT_NO_AUDIO
    letters = SyntheticLetterAudioSource(speech)

    store = SqliteStore(str(ensure_parent(database_path())))
    profile = _profile(store, language)

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
