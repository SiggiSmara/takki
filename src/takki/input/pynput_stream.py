import sys
from typing import Protocol

from takki.input import EventSink, KeyEvent

if sys.platform == "win32":
    import pynput.keyboard as keyboard

    # Module level (not nested in __init__) so windows_only tests can import
    # and exercise the translation directly, without a live Listener.
    def translate(key: keyboard.Key | keyboard.KeyCode, pressed: bool) -> KeyEvent:
        if isinstance(key, keyboard.KeyCode):
            return KeyEvent(pressed=pressed, char=key.char, name=None)
        return KeyEvent(pressed=pressed, char=None, name=key.name)


class _Listener(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class PynputKeyStream:
    # Declared at class level, outside the platform guard below: pyright's
    # sys.platform reachability elimination (pythonPlatform inferred as
    # Linux on this dev box) drops attributes assigned only inside an
    # unreachable `if sys.platform == "win32":` branch, so start()/stop()
    # below would see it as unknown otherwise. _Listener (not
    # pynput.keyboard.Listener) keeps this annotation off a pynput type.
    _listener: _Listener

    def __init__(self, outbound: EventSink) -> None:
        if sys.platform == "win32":

            def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
                if key is not None:
                    outbound.put(translate(key, pressed=True))

            def on_release(key: keyboard.Key | keyboard.KeyCode | None) -> None:
                if key is not None:
                    outbound.put(translate(key, pressed=False))

            self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        else:
            raise NotImplementedError("PynputKeyStream requires Windows")

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()
