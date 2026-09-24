"""
Spike: environment capture for docs/research/windows-validation.md tier A

Alpha session 12b-1 (2026-09-24). Answers A1, A2, A3, A4, A5 and the
find_voice half of A4b by machine, through the same calls main() makes, and
prints one paste-ready line per row. Changes nothing: no layout is loaded or
activated, no file is created, config is not edited.

Run from repo root on the Windows laptop:
    uv run python spikes/windows_env_capture.py

A3 reads the active layout exactly as main() does -- GetKeyboardLayout(0) on
the calling thread before any window exists -- so run it from a console with
the layout you intend to launch Takki on. The "Installed layouts" block reads
every layout in the user's list by HKL (GetKeyboardLayoutList, nothing
loaded) and says what verify_layout would answer for it, which predicts A3b
and the layout half of A4b without switching anything.
"""

import os
import platform
import subprocess
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from takki.platform.layout import Layout

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ANCHORS = ((2, 4), (3, 4), (4, 4), (2, 7), (3, 7), (4, 7))
LANGUAGES = ("en", "de", "is")


def _known_folder_documents() -> str:
    import ctypes
    import uuid

    folder_id = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")  # FOLDERID_Documents
    guid = (ctypes.c_ubyte * 16).from_buffer_copy(folder_id.bytes_le)
    path = ctypes.c_wchar_p()
    hr = ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(path))
    if hr != 0:
        return f"(SHGetKnownFolderPath failed 0x{hr & 0xFFFFFFFF:08x})"
    value = path.value or ""
    ctypes.windll.ole32.CoTaskMemFree(path)
    return value


def _windows_build() -> str:
    import winreg

    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
    product = winreg.QueryValueEx(key, "ProductName")[0]
    display = winreg.QueryValueEx(key, "DisplayVersion")[0]
    build = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
    ubr = winreg.QueryValueEx(key, "UBR")[0]
    # ProductName still says "Windows 10" on Windows 11; the build number is
    # the truth (>= 22000 is 11).
    if int(build) >= 22000:
        product = product.replace("Windows 10", "Windows 11")
    return f"{product} {display} (build {build}.{ubr})"


def _raw_locale() -> str:
    import ctypes

    buf = ctypes.create_unicode_buffer(85)
    ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85)
    return buf.value


def _installed_hkls() -> list[int]:
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.WinDLL("user32")
    user32.GetKeyboardLayoutList.restype = ctypes.c_int
    user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.wintypes.HKL)]
    count = user32.GetKeyboardLayoutList(0, None)
    buffer = (ctypes.wintypes.HKL * count)()
    user32.GetKeyboardLayoutList(count, buffer)
    return [h or 0 for h in buffer]


def _anchors(layout: "Layout") -> str:
    at = {(k.row, k.col): name for name, k in layout.keys.items()}
    return " ".join(f"({r},{c})={at.get((r, c), 'MISSING')}" for r, c in ANCHORS)


def _account() -> str:
    """G1 needs a standard account; say what this one is."""
    import ctypes

    elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
    try:
        groups = subprocess.run(
            ["whoami", "/groups", "/fo", "csv"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "account type unknown"
    admins = next((line for line in groups.splitlines() if "S-1-5-32-544" in line), None)
    if admins is None:
        return "standard account"
    if elevated:
        return "administrator, **elevated**"
    return "administrator, not elevated (filtered token)"


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() + (" (modified tracked files)" if dirty.stdout.strip() else "")


def main() -> None:
    if sys.platform != "win32":
        print(
            "FAIL: Windows-only. Run it on the laptop: uv run python spikes/windows_env_capture.py"
        )
        sys.exit(1)

    import pygame

    from takki import config
    from takki.data_dir import database_path
    from takki.main import resolve_language, verify_layout
    from takki.platform.windows import WindowsPlatformInterface, language_for_hkl, read_layout

    windows = WindowsPlatformInterface()
    rows: list[tuple[str, str]] = []

    # A1
    documents = _known_folder_documents()
    onedrive = "OneDrive" in documents
    sdl = ".".join(str(p) for p in pygame.get_sdl_version())
    rows.append(
        (
            "A1",
            f"{_windows_build()}; Python {platform.python_version()}; "
            f"pygame {pygame.version.ver} / SDL {sdl}; Documents = `{documents}` "
            f"({'**OneDrive-redirected**' if onedrive else 'not OneDrive-redirected'}); {_account()}; "
            f"commit {_git_head()}",
        )
    )

    # A2
    raw = _raw_locale()
    system_language = windows.get_system_language()
    verdict = "pass" if system_language == "en" else "**FAIL** (expected `en`)"
    rows.append(("A2", f"`{system_language}` from raw locale `{raw}` -- {verdict}"))

    # A3 -- the call main() makes, then the check main() makes
    layout = windows.get_layout_positions()
    language = resolve_language(windows)
    anchors = _anchors(layout)
    anchors_ok = "MISSING" not in anchors
    mismatch = verify_layout(language, layout)
    a3_ok = anchors_ok and layout.lang == "en" and mismatch is None
    # A3 reads the active layout on purpose -- it is what main() will see -- so
    # it cannot be forced, only reported. A non-US reading is precondition P4
    # not met rather than a defect, and says so.
    a3_verdict = "pass" if a3_ok else "**FAIL**"
    if layout.lang != "en":
        a3_verdict = "**P4 not met** (switch to English (US) with Win+Space and rerun)"
    rows.append(
        (
            "A3",
            f"{a3_verdict} -- `Layout.lang` = `{layout.lang}` (locale `{raw}`); "
            f"{len(layout.graphemes)} graphemes, {len(layout.keys)} keys; anchors {anchors}; "
            f"verify_layout({language!r}) = "
            f"{'None (would start)' if mismatch is None else repr(mismatch)}",
        )
    )

    # A4 -- where the file is, not where it should be
    db = database_path()
    wal = db.with_name(db.name + "-wal")
    shm = db.with_name(db.name + "-shm")
    candidates = {
        os.path.normcase(p): p
        for p in (os.path.join(documents, "Takki"), os.path.expanduser(r"~\Documents\Takki"))
    }
    stray = [p for p in candidates.values() if os.path.exists(p)]
    expected = os.path.join(os.environ.get("LOCALAPPDATA", "?"), "Takki", "takki.sqlite")
    if not db.exists():
        a4 = f"**not yet created** -- launch Takki once, then re-run. Resolves to `{db}`"
    else:
        # A Documents\Takki older than the database is a leftover from before the
        # 2026-09-20 data-directory decision, not something this build created.
        db_born = db.stat().st_ctime
        created_by_this_build = [p for p in stray if os.stat(p).st_ctime >= db_born]
        a4_ok = (
            os.path.normcase(str(db)) == os.path.normcase(expected) and not created_by_this_build
        )
        stray_text = (
            ", ".join(
                f"`{p}` (created {time.strftime('%Y-%m-%d %H:%M', time.localtime(os.stat(p).st_ctime))}, "
                f"{len(os.listdir(p))} entries, "
                f"{'newer than the database: created by this build' if p in created_by_this_build else 'older than the database: pre-2026-09-20 leftover'})"
                for p in stray
            )
            if stray
            else "none"
        )
        # The sidecars exist only while a connection is open (a clean close
        # checkpoints and deletes them), so ask the file which journal it uses.
        from takki.progress_dump import connect_readonly

        conn = connect_readonly(db)
        try:
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        a4_ok = a4_ok and journal == "wal"
        a4 = (
            f"{'pass' if a4_ok else '**FAIL**'} -- `{db}` ({db.stat().st_size} bytes); journal_mode `{journal}`; "
            f"-wal {'present' if wal.exists() else 'absent'}, -shm {'present' if shm.exists() else 'absent'}; "
            f"stray Documents\\Takki: {stray_text}"
        )
    rows.append(("A4", a4))

    # A4b -- the registry half. The launch half is by hand (Running order).
    voices = {lang: windows.find_voice(lang) for lang in LANGUAGES}
    voices_ok = (
        voices["en"] is not None
        and voices["de"] is not None
        and voices["is"] is None
        and all(v.startswith("HKEY_") for v in voices.values() if v is not None)
    )
    rows.append(
        (
            "A4b",
            f"find_voice: {'pass' if voices_ok else '**FAIL**'} -- "
            + "; ".join(f"`{lang}` -> `{voices[lang]}`" for lang in LANGUAGES)
            + ". Launch half: by hand",
        )
    )

    # A5 -- whatever is running right now; the NVDA half is by hand
    reader = windows.detect_screen_reader()
    rows.append(
        ("A5", f"`{reader}` (NVDA {'running' if reader == 'nvda' else 'not running'} at capture)")
    )

    # A Win+Space mid-capture would leave A3 describing a layout the rest of
    # the run never saw; read it again at the end and say so.
    layout_after = windows.get_layout_positions()
    if layout_after.lang != layout.lang:
        rows[2] = (
            "A3",
            f"**INVALID** -- the active layout changed during the capture "
            f"(`{layout.lang}` at A3, `{layout_after.lang}` at the end); rerun without switching",
        )

    print(f"config.LANGUAGE = {config.LANGUAGE!r} (resolved language: {language!r})\n")
    print("Installed layouts (read by HKL, nothing activated):")
    for hkl in _installed_hkls():
        lang = language_for_hkl(hkl)
        read = read_layout(hkl)
        against = {want: verify_layout(want, read) for want in LANGUAGES}
        own = against.get(lang)
        print(
            f"  HKL {hkl & 0xFFFFFFFF:08x}  lang={lang:<3} {len(read.graphemes):>2} graphemes  "
            f"own table: {'matches' if own is None and lang in LANGUAGES else own!r}"
        )
        for want in LANGUAGES:
            if want != lang:
                print(f"      as {want!r}: {against[want]!r}")

    print("\nResult column, one row per line:\n")
    for check_id, text in rows:
        print(f"{check_id}: {text}")


if __name__ == "__main__":
    main()
