"""Reproduce CI's pyright condition locally: the Windows pass with Windows deps ABSENT.

Written 2026-09-20, alpha session 12a-2, after the first push went red on a file
that was green in both pyright passes on the Windows laptop.

The two-pass setup in .pre-commit-config.yaml assumes `--pythonplatform Windows`
checks the Windows half of the codebase. It does, but only as far as the
*environment* allows: a Windows-only dependency is not installed on Linux, so
that pass cannot resolve it there. `comtypes` is `sys_platform == 'win32'` in
pyproject.toml, so CI's Linux job reported two unresolvable imports in
`src/takki/audio/sapi_tts.py` that the laptop could never see -- the laptop has
comtypes installed, which is exactly what CI lacks.

This hides the package, runs the Windows pass, and puts it back, so the claim in
ADR-019 § Headless audio/video stays checkable rather than becoming folklore.
Restoration is in a finally block: an interrupted run must not leave the venv
broken.

    uv run python spikes/pyright_ci_condition_spike.py

Measured 2026-09-20: 2 errors before the `# pyright: ignore[reportMissingImports]`
comments were added, 0 after. Note what the suppression does NOT buy back -- an
unresolved import makes pyright treat that module as Unknown, so nothing is
type-checked *through* comtypes on the Linux run. The Windows pass on Linux is
strictly weaker than the same pass on Windows, and the way to close that is to
run pyright on the windows-latest job too.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / ".venv" / "Lib" / "site-packages"
# Every distribution that is Windows-only in pyproject.toml and that `src/`
# imports directly. pynput is deliberately not here: pyright bundles stubs for
# it, so it degrades to a warning rather than an error.
WINDOWS_ONLY = ["comtypes"]


def main() -> None:
    if sys.platform != "win32":
        print("This spike hides a Windows-only package; run it on the Windows laptop.")
        return

    moved: list[tuple[Path, Path]] = []
    try:
        for name in WINDOWS_ONLY:
            for path in sorted(SITE.glob(f"{name}*")):
                hidden = path.with_name(path.name + ".__hidden__")
                shutil.move(str(path), str(hidden))
                moved.append((hidden, path))
        print(f"hidden: {[original.name for _, original in moved]}\n")
        result = subprocess.run(
            ["uv", "run", "pyright", "--pythonplatform", "Windows"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        for line in output.splitlines():
            if "error" in line or "informations" in line:
                print(line)
        print(f"\nexit code: {result.returncode}  (0 means CI's Linux job would pass)")
    finally:
        for hidden, original in moved:
            shutil.move(str(hidden), str(original))
        print(f"restored: {[original.name for _, original in moved]}")
        for name in WINDOWS_ONLY:
            print(f"  {name} present again: {(SITE / name).exists()}")


if __name__ == "__main__":
    main()
