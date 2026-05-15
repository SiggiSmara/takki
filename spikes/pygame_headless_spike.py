"""
Spike: pygame.mixer audio without a display window

Tests that pygame.mixer can play sound cues on Windows without
initialising pygame.display (i.e. no window appears).

This matters because the visual display in Takki is optional and off
by default — the app must be fully functional as audio-only.

Run from repo root on the Windows laptop:
    uv run python spikes/pygame_headless_spike.py

What this checks:
  1. pygame.mixer initialises without pygame.display
  2. A synthesised beep tone plays to completion
  3. No window appears at any point
  4. Mixer shuts down cleanly

You should hear two short beeps and see OK results for each step.
"""

import sys
import time
import wave
import struct
import math
import tempfile
import os


SAMPLE_RATE = 22050


def section(title: str) -> None:
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


def make_beep_wav(path: str, frequency: float, duration: float) -> None:
    """Write a pure-tone WAV to path. No dependencies beyond stdlib."""
    n_frames = int(SAMPLE_RATE * duration)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        for i in range(n_frames):
            value = int(32767 * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE))
            wav.writeframes(struct.pack("<h", value))


def check_import() -> bool:
    section("1. Import check")
    try:
        import pygame  # noqa: F401
        print(f"OK: pygame {pygame.version.ver} imported")
        return True
    except ImportError as e:
        print(f"FAIL: could not import pygame: {e}")
        return False


def init_mixer_only() -> bool:
    section("2. Initialise mixer WITHOUT display")
    try:
        import pygame
        pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
        pygame.mixer.init()
        print("OK: pygame.mixer initialised")
        print(f"    Frequency : {pygame.mixer.get_init()[0]} Hz")
        print(f"    Channels  : {pygame.mixer.get_init()[2]}")
        print("    pygame.display was NOT initialised — no window")
        return True
    except Exception as e:
        print(f"FAIL: mixer init error: {e}")
        return False


def play_beep(label: str, frequency: float) -> bool:
    section(f"3. Play beep — {label} ({frequency:.0f} Hz)")
    try:
        import pygame
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        make_beep_wav(wav_path, frequency, duration=0.4)
        sound = pygame.mixer.Sound(wav_path)
        t0 = time.perf_counter()
        sound.play()
        # Wait for playback to finish
        while pygame.mixer.get_busy():
            time.sleep(0.01)
        elapsed = time.perf_counter() - t0
        os.unlink(wav_path)
        print(f"OK: beep played ({elapsed:.2f}s)")
        return True
    except Exception as e:
        print(f"FAIL: playback error: {e}")
        return False


def check_no_display() -> None:
    section("4. Confirm display was never initialised")
    import pygame
    if pygame.display.get_init():
        print("WARN: pygame.display is initialised — a window may have appeared")
    else:
        print("OK: pygame.display was never initialised (no window opened)")


def quit_mixer() -> None:
    section("5. Clean shutdown")
    import pygame
    pygame.mixer.quit()
    print("OK: mixer shut down cleanly")


def main() -> None:
    print("pygame Headless Audio Spike")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")

    if not check_import():
        sys.exit(1)

    if not init_mixer_only():
        sys.exit(1)

    play_beep("correct keypress tone", frequency=880.0)
    time.sleep(0.2)
    play_beep("wrong keypress tone", frequency=220.0)

    check_no_display()
    quit_mixer()

    print("\n" + "="*50)
    print("  DONE")
    print("="*50)
    print("\nPaste the full output of this script back into the Claude Code session.")


if __name__ == "__main__":
    main()
