"""
Spike: Windows keyboard layout reading — the four assumptions #12a-1 rests on

Written 2026-09-20, before implementing WindowsPlatformInterface.get_layout_positions().
The alpha-plan row names two assumptions to verify first; two more turned up
while writing this. All four are cheap to check and expensive to be wrong about:

  A1  LoadKeyboardLayout succeeds for a KLID that is NOT in the user's preload
      list. If true, CI can test en/de/is on any runner. If false, the layout
      tests only ever run on a machine that happens to have them installed.
  A2  ToUnicodeEx is correct against a loaded-but-never-activated HKL, so the
      reader can be parameterised on HKL and tested without touching OS state.
  A3  The dead-key state problem: ToUnicodeEx returns -1 for a dead key AND
      leaves state in the kernel that corrupts the NEXT call. Does the
      documented wFlags bit 2 ("do not change keyboard state", Win10 1607+)
      actually suppress it?
  A4  The hard-coded scan-code -> (row, col) grid agrees with build_en/de/is
      exactly. An off-by-one here reassigns fingers via COL_TO_FINGER, so this
      is checked against all three tables, not eyeballed.

Run from repo root on Windows:
    uv run python spikes/layout_reader_spike.py
"""

import ctypes
import ctypes.wintypes
import sys

from takki.platform.layout import build_de, build_en, build_is, key_positions

if sys.platform != "win32":
    raise SystemExit("Windows only")

user32 = ctypes.WinDLL("user32", use_last_error=True)

KLF_NOTELLSHELL = 0x00000080
MAPVK_VSC_TO_VK_EX = 3
NO_KERNEL_STATE_CHANGE = 0x4  # wFlags bit 2, Win10 1607+

user32.LoadKeyboardLayoutW.restype = ctypes.wintypes.HKL
user32.GetKeyboardLayout.restype = ctypes.wintypes.HKL
user32.MapVirtualKeyExW.restype = ctypes.wintypes.UINT

# Scan-code -> (row, col). Set-1 scan codes are positional: the physical key,
# not the character it produces. Rows run left to right from the outer edge.
_GRID: dict[int, tuple[int, int]] = {}
for _col, _sc in enumerate(range(0x02, 0x0E), start=1):  # number row, 12 keys
    _GRID[_sc] = (1, _col)
for _col, _sc in enumerate(range(0x10, 0x1C), start=1):  # top alpha, 12 keys
    _GRID[_sc] = (2, _col)
for _col, _sc in enumerate(range(0x1E, 0x29), start=1):  # home, 11 keys
    _GRID[_sc] = (3, _col)
_GRID[0x2B] = (3, 12)  # the key right of the home row on ANSI/ISO
for _col, _sc in enumerate(range(0x2C, 0x36), start=1):  # bottom alpha, 10 keys
    _GRID[_sc] = (4, _col)

ISO_EXTRA = 0x56  # the extra key left of Z on ISO keyboards; no grid slot yet

LAYOUTS = {"en": "00000409", "de": "00000407", "is": "0000040F"}
NOT_INSTALLED = "0000040C"  # French, expected absent on this laptop


def read(hkl: int, scan_code: int, flags: int = 0) -> tuple[int, str]:
    vk = user32.MapVirtualKeyExW(scan_code, MAPVK_VSC_TO_VK_EX, hkl)
    if not vk:
        return 0, ""
    state = (ctypes.c_ubyte * 256)()
    buf = ctypes.create_unicode_buffer(8)
    count = user32.ToUnicodeEx(vk, scan_code, state, buf, len(buf), flags, hkl)
    return count, buf[: max(count, 0)]


def flush(hkl: int) -> int:
    """Consume any pending dead-key state for this layout. Returns calls needed.

    NO_KERNEL_STATE_CHANGE stops a call *creating* pending state; it does not
    let a call *consume* state already pending, so a contaminated layout stays
    contaminated forever under the flag. Space composes with a pending dead
    key and clears it.
    """
    for n in range(1, 8):
        count, _ = read(hkl, 0x39)  # space, unflagged: it must change state
        if count >= 0:
            return n
    return -1


def installed() -> list[int]:
    n = user32.GetKeyboardLayoutList(0, None)
    arr = (ctypes.wintypes.HKL * n)()
    user32.GetKeyboardLayoutList(n, arr)
    return [h for h in arr]


def main() -> None:
    print("=== active / installed ===")
    active = user32.GetKeyboardLayout(0)
    print(f"GetKeyboardLayout(0) = 0x{active & 0xFFFFFFFF:08x}  langid=0x{active & 0x3FF:03x}")
    for h in installed():
        print(f"  installed 0x{h & 0xFFFFFFFF:08x}  langid low10=0x{h & 0x3FF:03x}")

    print("\n=== A1: LoadKeyboardLayout for a NON-preloaded KLID ===")
    hkl_fr = user32.LoadKeyboardLayoutW(NOT_INSTALLED, KLF_NOTELLSHELL)
    err = ctypes.get_last_error()
    print(f"LoadKeyboardLayoutW({NOT_INSTALLED}) -> 0x{(hkl_fr or 0) & 0xFFFFFFFF:08x} err={err}")
    if hkl_fr:
        # AZERTY discriminator: (2,1) is 'a' on French, 'q' on QWERTY.
        print(f"  scan 0x10 (2,1) reads {read(hkl_fr, 0x10)!r}   <- 'a' means a real French layout")
        print(f"  was it added to the installed list? {hkl_fr in installed()}")

    print("\n=== A2: read each target layout without activating it ===")
    handles: dict[str, int] = {}
    for code, klid in LAYOUTS.items():
        h = user32.LoadKeyboardLayoutW(klid, KLF_NOTELLSHELL)
        handles[code] = h
        print(f"{code}: klid={klid} hkl=0x{(h or 0) & 0xFFFFFFFF:08x} langid=0x{h & 0x3FF:03x}")
    print(f"active layout unchanged after loading? {user32.GetKeyboardLayout(0) == active}")
    print("  discriminator (2,6) — y on en/is, z on de:")
    for code, h in handles.items():
        print(f"    {code}: {read(h, 0x15)!r}")

    print("\n=== A3: dead key behaviour and state contamination ===")
    h_is = handles["is"]
    print(f"is (3,11) 0x28 acute:      {read(h_is, 0x28)!r}   (-1 == dead key)")
    print(f"is (3,1)  0x1E right after: {read(h_is, 0x1E)!r}   <- 'á' means contaminated")
    print(f"is (3,1)  0x1E again:       {read(h_is, 0x1E)!r}")
    print("  with NO_KERNEL_STATE_CHANGE (wFlags bit 2):")
    print(f"    0x28 acute:  {read(h_is, 0x28, NO_KERNEL_STATE_CHANGE)!r}")
    print(f"    0x1E after:  {read(h_is, 0x1E, NO_KERNEL_STATE_CHANGE)!r}   <- 'a' means clean")
    print(f"  de (1,12) 0x0D acute:      {read(handles['de'], 0x0D)!r}")

    print("\n=== A4: grid vs build_en/de/is ===")
    for code, builder in (("en", build_en), ("de", build_de), ("is", build_is)):
        h = handles[code]
        print(f"{code}: flush took {flush(h)} call(s)")
        seen: dict[str, tuple[int, int]] = {}
        extras: list[str] = []
        for sc, pos in sorted(_GRID.items()):
            count, chars = read(h, sc, NO_KERNEL_STATE_CHANGE)
            if count == 1 and chars.isalpha():
                seen[chars.lower()] = pos
            elif count != 1 or chars.strip():
                extras.append(f"0x{sc:02x}{pos}={count}:{chars!r}")
        want = {k: v for k, v in key_positions(builder()).items() if k != "dead-acute"}
        missing = sorted(set(want) - set(seen))
        unexpected = sorted(set(seen) - set(want))
        moved = sorted(k for k in set(want) & set(seen) if want[k] != seen[k])
        status = "MATCH" if not (missing or unexpected or moved) else "DIFF"
        print(f"{code}: {status} letters={len(seen)} expected={len(want)}")
        if missing:
            print(f"   missing: {missing}")
        if unexpected:
            print(f"   unexpected: {unexpected}")
        if moved:
            print(f"   moved: {[(k, seen[k], want[k]) for k in moved]}")
        print(f"   non-letter keys swept: {' '.join(extras)}")
        iso = read(h, ISO_EXTRA, NO_KERNEL_STATE_CHANGE)
        print(f"   ISO extra 0x56: {iso!r}")


def cleanup(before: set[int]) -> None:
    # KLF_NOTELLSHELL does NOT keep a loaded layout out of GetKeyboardLayoutList,
    # so anything this spike added is unloaded again. Only ones it added --
    # unloading a layout the user really installed would remove it for them.
    for h in set(installed()) - before:
        ok = user32.UnloadKeyboardLayout(ctypes.wintypes.HKL(h))
        print(f"unloaded 0x{h & 0xFFFFFFFF:08x} -> {bool(ok)}")


if __name__ == "__main__":
    _before = set(installed())
    try:
        main()
    finally:
        print("\n=== cleanup ===")
        cleanup(_before)
        print(f"installed now: {[f'0x{h & 0xFFFFFFFF:08x}' for h in installed()]}")
