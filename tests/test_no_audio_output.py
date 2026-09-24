"""Startup on a machine with a voice and nowhere to play it.

The one environment that reproduces this for real is a GitHub windows-latest
runner: David is in the registry, COM initialises, and SpVoice.Speak raises
COMError 0x8004503A (alpha session 12a-2, ADR-019 § Headless audio/video). The
laptop cannot run this test and the runner cannot run test_sapi_tts.py -- each
proves what the other cannot reach. If this starts failing on the runner because
GitHub gave it a sound device, the test has lost its machine, not found a bug.
"""

import queue
import sys
import time

import pytest

from takki.audio.tts import SpeechOutputError
from takki.audio.tts_worker import SpeechFinished, TTSWorker

# Not `windows_only`: that tier is run by hand on the laptop, which has a
# device, so there this test can only fail. The body is Windows-guarded.
pytestmark = pytest.mark.no_audio_output


def test_startup_refuses_a_voice_that_cannot_sound() -> None:
    if sys.platform != "win32":
        return
    from takki.audio.sapi_tts import PROBE_SECONDS
    from takki.platform.windows import WindowsPlatformInterface

    platform = WindowsPlatformInterface()
    voice = platform.find_voice("en")
    # Asserted, not skipped: the point is that find_voice() passes here and
    # still cannot tell, so a runner without a voice is not this test's machine.
    assert voice is not None, "the runner is expected to have a SAPI voice"
    # The production path exactly as main() takes it -- factory, worker thread,
    # start() re-raising the build failure on the caller.
    worker = TTSWorker(platform.get_fallback_tts(voice), queue.Queue[SpeechFinished]())
    start = time.monotonic()
    with pytest.raises(SpeechOutputError):
        worker.start()
    assert time.monotonic() - start < PROBE_SECONDS + 10
