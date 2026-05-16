"""
Spike: faster-whisper latency and hardware capability profile

Measures end-to-end Whisper transcription latency for tiny/base/small models
on a fixed set of audio fixtures, alongside the hardware signals the ADR-018
detector will use. Goal: replace the unsourced "~500-800ms on CPU" figure in
CLAUDE.md with real numbers from both target machines (old headless Linux box
and the Windows laptop) so we can pick a sensible default Whisper model.

Run from repo root on each machine:
    uv run --with piper-tts --with py-cpuinfo --with psutil \\
        python spikes/whisper_latency_spike.py

Output: a printed report plus spikes/whisper_spike_results.json.
Paste the full stdout back into the Claude Code session.

Audio fixtures are generated once via Piper TTS and cached in spikes/.
Whisper models (~75MB tiny / ~145MB base / ~470MB small) download on first
run and are cached by faster-whisper under ~/.cache/huggingface/.
"""

import gc
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
import wave
from pathlib import Path

SPIKES_DIR = Path(__file__).parent
RESULTS_PATH = SPIKES_DIR / "whisper_spike_results.json"
PIPER_VOICE = "en_US-lessac-low"
PIPER_VOICE_PATH = SPIKES_DIR / f"{PIPER_VOICE}.onnx"

FIXTURES = [
    ("short",  "Faster."),
    ("medium", "Next lesson, please."),
    ("long",   "I want to change my voice to a different one."),
]

MODELS = ["tiny", "base", "small"]
RUNS_PER_CLIP = 3


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def system_report() -> dict[str, object]:
    section("1. System report")
    import psutil
    from cpuinfo import get_cpu_info

    info = get_cpu_info()
    vm = psutil.virtual_memory()
    du = psutil.disk_usage(str(SPIKES_DIR))

    flags = info.get("flags", []) or []
    relevant_flags = [f for f in ("sse4_1", "sse4_2", "avx", "avx2", "avx512f", "fma") if f in flags]

    report = {
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "cpu_brand": info.get("brand_raw", "unknown"),
        "cpu_arch": info.get("arch_string_raw", platform.machine()),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_hz_advertised_mhz": info.get("hz_advertised_friendly", "unknown"),
        "cpu_relevant_flags": relevant_flags,
        "ram_total_gb": round(vm.total / 1024**3, 2),
        "ram_available_gb": round(vm.available / 1024**3, 2),
        "disk_free_gb": round(du.free / 1024**3, 2),
        "gpu": detect_gpu(),
    }

    for k, v in report.items():
        print(f"  {k:26s} {v}")
    return report


def detect_gpu() -> str:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "none detected (CPU-only run)"


def cpu_microbenchmark() -> float:
    section("2. CPU microbenchmark (mirrors ADR-018 detector)")
    import numpy as np

    rng = np.random.default_rng(0)
    a = rng.standard_normal((512, 512), dtype=np.float32)
    b = rng.standard_normal((512, 512), dtype=np.float32)
    _ = a @ b  # warm-up

    runs = []
    for _ in range(5):
        t0 = time.perf_counter()
        _ = a @ b
        runs.append((time.perf_counter() - t0) * 1000)

    median = statistics.median(runs)
    print(f"  512x512 float32 matmul median: {median:.1f} ms (n=5)")
    print(f"  individual runs (ms): {[round(r, 1) for r in runs]}")
    return median


def ensure_piper_voice() -> bool:
    if PIPER_VOICE_PATH.exists():
        return True
    print(f"  downloading Piper voice {PIPER_VOICE} (~30 MB, one-time)...")
    result = subprocess.run(
        [sys.executable, "-m", "piper.download_voices",
         "--download-dir", str(SPIKES_DIR), PIPER_VOICE],
        capture_output=False,
    )
    return result.returncode == 0


def generate_fixtures() -> list[tuple[str, Path, float]]:
    section("3. Audio fixtures (generate via Piper if missing)")
    try:
        from piper.voice import PiperVoice
    except ImportError:
        print("  FAIL: piper not available. Re-run with --with piper-tts")
        sys.exit(1)

    if not ensure_piper_voice():
        print("  FAIL: could not download Piper voice")
        sys.exit(1)

    voice = PiperVoice.load(str(PIPER_VOICE_PATH))
    out: list[tuple[str, Path, float]] = []

    for name, phrase in FIXTURES:
        wav_path = SPIKES_DIR / f"whisper_fixture_{name}.wav"
        if not wav_path.exists():
            with wave.open(str(wav_path), "wb") as wf:
                voice.synthesize_wav(phrase, wf)
        with wave.open(str(wav_path), "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
        print(f"  {name:7s} {duration:5.2f}s   \"{phrase}\"   -> {wav_path.name}")
        out.append((name, wav_path, duration))

    return out


def benchmark_model(model_size: str,
                    fixtures: list[tuple[str, Path, float]]) -> dict[str, object]:
    section(f"4.{MODELS.index(model_size) + 1} Whisper model: {model_size}")
    import psutil
    from faster_whisper import WhisperModel

    proc = psutil.Process()
    gc.collect()
    rss_before = proc.memory_info().rss

    t0 = time.perf_counter()
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    load_time = time.perf_counter() - t0
    rss_after_load = proc.memory_info().rss
    load_rss_delta_mb = (rss_after_load - rss_before) / 1024**2

    print(f"  cold load: {load_time:.2f}s   "
          f"RSS delta after load: {load_rss_delta_mb:.0f} MB   "
          f"compute_type=int8")

    clip_results: list[dict[str, object]] = []
    for name, wav_path, duration in fixtures:
        latencies: list[float] = []
        transcript = ""
        for run in range(RUNS_PER_CLIP):
            t0 = time.perf_counter()
            segments, _info = model.transcribe(str(wav_path), language="en", beam_size=1)
            text = " ".join(seg.text.strip() for seg in segments)
            latencies.append(time.perf_counter() - t0)
            if run == 0:
                transcript = text.strip()

        lo, med, hi = min(latencies), statistics.median(latencies), max(latencies)
        rtf = med / duration
        print(f"  {name:7s} {duration:4.2f}s clip:  "
              f"min {lo*1000:6.0f} ms   median {med*1000:6.0f} ms   "
              f"max {hi*1000:6.0f} ms   RTF {rtf:.2f}")
        print(f"          transcript: \"{transcript}\"")
        clip_results.append({
            "clip": name,
            "duration_s": round(duration, 3),
            "latency_ms_min": round(lo * 1000, 1),
            "latency_ms_median": round(med * 1000, 1),
            "latency_ms_max": round(hi * 1000, 1),
            "rtf_median": round(rtf, 3),
            "transcript": transcript,
        })

    del model
    gc.collect()

    return {
        "model": model_size,
        "load_time_s": round(load_time, 2),
        "load_rss_delta_mb": round(load_rss_delta_mb, 1),
        "compute_type": "int8",
        "clips": clip_results,
    }


def summary_table(model_results: list[dict[str, object]]) -> None:
    section("5. Summary (paste this into the ADR discussion)")
    print(f"  {'model':6s} {'load':>7s} {'RAM':>7s}   {'short':>9s} {'medium':>9s} {'long':>9s}   {'med RTF':>8s}")
    print(f"  {'-' * 6:6s} {'-' * 7:>7s} {'-' * 7:>7s}   "
          f"{'-' * 9:>9s} {'-' * 9:>9s} {'-' * 9:>9s}   {'-' * 8:>8s}")
    for r in model_results:
        clips = {c["clip"]: c for c in r["clips"]}  # type: ignore[index]
        rtfs = [c["rtf_median"] for c in r["clips"]]  # type: ignore[index]
        med_rtf = statistics.median(rtfs)
        print(f"  {r['model']:6s} "
              f"{r['load_time_s']:>5.2f}s  "
              f"{r['load_rss_delta_mb']:>5.0f}MB   "
              f"{clips['short']['latency_ms_median']:>6.0f} ms "
              f"{clips['medium']['latency_ms_median']:>6.0f} ms "
              f"{clips['long']['latency_ms_median']:>6.0f} ms   "
              f"{med_rtf:>8.2f}")


def main() -> None:
    print("Whisper Latency Spike")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Working dir: {os.getcwd()}")

    sys_info = system_report()
    matmul_ms = cpu_microbenchmark()
    fixtures = generate_fixtures()

    section("4. Whisper benchmarks (cold load + 3 runs per clip per model)")
    print(f"  Models will download on first run (~700 MB total cached under huggingface).")
    print(f"  Free disk: {shutil.disk_usage(SPIKES_DIR).free / 1024**3:.1f} GB")

    model_results = [benchmark_model(m, fixtures) for m in MODELS]
    summary_table(model_results)

    results = {
        "system": sys_info,
        "cpu_matmul_median_ms_512x512_f32": round(matmul_ms, 2),
        "models": model_results,
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\n  Results JSON written to {RESULTS_PATH}")
    print("\n" + "=" * 60)
    print("  DONE - paste the full output above back to Claude.")
    print("=" * 60)


if __name__ == "__main__":
    main()
