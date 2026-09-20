"""TTSEngine over SAPI's SpVoice, driven directly rather than through pyttsx3.

Alpha session 12a-2 replaced pyttsx3 on Windows. pyttsx3 leaves its own
`DriverProxy._busy` False after the first `runAndWait()`, so from the second
utterance on it runs `driver.say()` outside its loop and then immediately pumps
the queued `endLoop` command -- whose `driver.stop()` fires
`Speak("", SPF_PURGEBEFORESPEAK)` at the utterance that has just started. That
is the truncation recorded in concurrency-model.md, measured here and traced to
that line. It also rejects OneCore voice ids and swallows the ValueError, so a
verified voice silently does not apply.

Driving SpVoice directly removes all of it, and removes the COM event sink with
it: nothing here registers for events, so no thread has to pump a message queue
and `stop()` costs the caller nothing (it sets a flag and makes no COM call).
"""

import sys
import threading
from typing import Any

if sys.platform == "win32":
    # Module level, and that placement is the fix for a real failure: comtypes
    # initialises COM on whichever thread first imports it, and as an STA. Let
    # the TTS worker be that thread and it is pinned to an STA before SapiTTS
    # can ask for the MTA it needs, and CoInitializeEx fails with
    # RPC_E_CHANGED_MODE. This module is imported from get_fallback_tts(), on
    # the main thread, which is where an STA is what everything else already
    # assumes anyway.
    import comtypes
    import comtypes.client

# SpeechVoiceSpeakFlags. Async because a synchronous Speak() holds SAPI inside
# one call for the length of the utterance, where a purge cannot reach it.
_SPF_ASYNC = 1
_SPF_PURGE_BEFORE_SPEAK = 2

# How often the worker looks at the cancel flag while an utterance is sounding.
# It is the audio-stop latency and it is worker time, never the main thread's.
_POLL_MS = 10

# ADR-003 § SAPI fallback rate mapping: round((1.0 - length_scale) * 10) with
# the default length_scale of 1.0. Pinned rather than inherited, because the
# inherited value is whatever the machine's SAPI default happens to be.
_RATE = 0


class SapiTTS:
    """Blocking TTSEngine over SAPI. Construct it on the TTS worker thread."""

    # Declared here, not just assigned in __init__: on pyright's Linux pass the
    # body below the platform guard is unreachable, so the assignments are
    # invisible and every use in speak()/stop() reads as an unknown attribute.
    _cancel: threading.Event
    _voice: Any  # SAPI's SpVoice; comtypes ships no stubs

    def __init__(self, voice_id: str | None = None) -> None:
        if sys.platform != "win32":
            raise NotImplementedError("SapiTTS requires Windows")

        # This thread's own apartment, and MTA on purpose: it blocks in
        # WaitUntilDone and never pumps messages, which is exactly what an STA
        # thread may not do. It raises RPC_E_CHANGED_MODE rather than degrading
        # if the thread was already claimed -- a loud failure at startup, not a
        # worker that mysteriously stops speaking later.
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        self._cancel = threading.Event()
        self._voice = comtypes.client.CreateObject("SAPI.SpVoice")
        self._voice.Rate = _RATE
        if voice_id is not None:
            # Not SpVoice.GetVoices(): that enumerates the SAPI5 category only,
            # and Windows 11's "Manage voices" -- the remedy main.py prints --
            # installs into Speech_OneCore. SetId takes either category's path.
            token = comtypes.client.CreateObject("SAPI.SpObjectToken")
            token.SetId(voice_id)
            self._voice.Voice = token

    def speak(self, text: str) -> None:
        # Deliberately does not clear the flag: the worker does that before it
        # dequeues, so a stop() arriving any time after that belongs to this
        # utterance. See TTSEngine.clear_cancel().
        if self._cancel.is_set():
            return
        self._voice.Speak(text, _SPF_ASYNC)
        while not self._voice.WaitUntilDone(_POLL_MS):
            if self._cancel.is_set():
                self._voice.Speak("", _SPF_PURGE_BEFORE_SPEAK)
                return

    def stop(self) -> None:
        # Callable from any thread and free on the caller: no COM call crosses
        # a thread here, so concurrency-model.md rule 4's whitelist is empty on
        # this path. The purge is issued by the worker itself, in speak().
        self._cancel.set()

    def clear_cancel(self) -> None:
        self._cancel.clear()
