"""
Spike: Piper TTS native Windows support

Tests that piper-tts installs and runs natively on Windows without WSL,
and that voice model download + synthesis work as expected.

Run from repo root on the Windows laptop:
    uv run --with piper-tts python spikes/piper_tts_spike.py

What this checks:
  1. piper-tts imports correctly
  2. A small voice model can be downloaded
  3. Synthesis produces a valid WAV file
  4. Synthesis latency is acceptable for TTS use

Expected output: a file spike_piper_output.wav in the spikes/ directory.
Open it in any audio player to verify voice quality.
"""

import sys
import time
import wave
import subprocess

VOICE_NAME = "en_US-lessac-low"
VOICE_DIR = "spikes"
OUTPUT_WAV = "spikes/spike_piper_output.wav"
TEST_PHRASE = "Hello. This is a test of the Piper text to speech engine."


def section(title: str) -> None:
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


def check_import() -> bool:
    section("1. Import check")
    try:
        from piper import PiperVoice  # noqa: F401
        print("OK: piper imported successfully")
        return True
    except ImportError as e:
        print(f"FAIL: could not import piper: {e}")
        print("      Make sure you ran: uv run --with piper-tts python spikes/piper_tts_spike.py")
        return False


def download_voice() -> bool:
    section("2. Voice model download")
    print(f"Downloading voice: {VOICE_NAME}")
    print("(This is a one-time download of ~30MB — subsequent runs use the cache)\n")
    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "piper.download_voices", "--download-dir", VOICE_DIR, VOICE_NAME],
        capture_output=False,
    )
    elapsed = time.perf_counter() - t0
    if result.returncode == 0:
        print(f"OK: voice model ready ({elapsed:.1f}s)")
        return True
    else:
        print(f"FAIL: download failed (return code {result.returncode})")
        return False


def synthesize() -> bool:
    section("3. Synthesis")
    try:
        from pathlib import Path
        from piper.voice import PiperVoice

        model_path = Path(VOICE_DIR) / f"{VOICE_NAME}.onnx"
        print(f"Loading model from: {model_path}")

        t0 = time.perf_counter()
        voice = PiperVoice.load(str(model_path))
        load_time = time.perf_counter() - t0
        print(f"OK: model loaded ({load_time:.2f}s)")

        t0 = time.perf_counter()
        with wave.open(OUTPUT_WAV, "wb") as wav_file:
            voice.synthesize_wav(TEST_PHRASE, wav_file)
        synth_time = time.perf_counter() - t0
        print(f"OK: synthesis complete ({synth_time:.2f}s)")
        print(f"    Phrase: \"{TEST_PHRASE}\"")
        print(f"    Output: {OUTPUT_WAV}")
        return True

    except Exception as e:
        print(f"FAIL: synthesis error: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_wav() -> None:
    section("4. WAV verification")
    try:
        with wave.open(OUTPUT_WAV, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            duration = frames / rate
        print(f"OK: valid WAV file")
        print(f"    Duration : {duration:.2f}s")
        print(f"    Sample rate: {rate} Hz")
        print(f"    Frames: {frames}")
        import os
        size_kb = os.path.getsize(OUTPUT_WAV) / 1024
        print(f"    File size: {size_kb:.1f} KB")
    except Exception as e:
        print(f"FAIL: WAV verification error: {e}")


def main() -> None:
    print("Piper TTS Spike")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")

    if not check_import():
        sys.exit(1)

    if not download_voice():
        sys.exit(1)

    if not synthesize():
        sys.exit(1)

    verify_wav()

    print("\n" + "="*50)
    print("  DONE")
    print("="*50)
    print(f"\nOpen {OUTPUT_WAV} to check voice quality.")
    print("Paste the full output of this script back into the Claude Code session.")


if __name__ == "__main__":
    main()
