"""
Spike: where should Takki take its characters from? (alpha-plan #13)

Opens a window like PygameFocusSource's, optionally starts a pynput hook beside
it, and logs every key on one clock from three places:

  hook  pynput's low-level hook: KeyCode char / is_dead / vk, the raw
        KBDLLHOOKSTRUCT scan code, and what production translate() makes of it
  raw   SDL's own events, read by an SDL event filter installed in front of
        pygame's, so nothing pygame drops (auto-repeat KEYDOWNs) is hidden
  pg    what pygame.event.get() hands back, which is what Takki would read

Each run is a list of steps shown in the window. Left-click the window for the
next step, right-click to redo the current one. The click that brings the
window back into focus is not delivered by SDL, and clicks within 500 ms of
focus coming back are ignored as well, so clicking back in never advances.

Runs (start each on the layout named; the window shows the active layout):
    is      Icelandic, hook + window
    de      German, hook + window
    switch  starts on English (US), switches layout mid-run
    window  Icelandic, window only (no hook)

    uv run python spikes/key_capture_source_spike.py <run> [log_path]

Log: JSON lines, default spikes/results/key_capture_source/<run>-<stamp>.jsonl.
Read it with spikes/key_capture_source_analyse.py.
"""

import ctypes
import ctypes.wintypes as wt
import json
import queue
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.platform != "win32":
    raise SystemExit("Windows only")

import pygame

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.GetKeyboardLayout.argtypes = [wt.DWORD]
user32.MapVirtualKeyExW.restype = wt.UINT
user32.MapVirtualKeyExW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p]
user32.ToUnicodeEx.restype = ctypes.c_int
user32.ToUnicodeEx.argtypes = [
    wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_ubyte), wt.LPWSTR, ctypes.c_int, wt.UINT,
    ctypes.c_void_p,
]

# Windows set-1 scan code (+ extended flag) -> SDL scancode, for the keys the steps use.
# Mirrors SDL 2's windows_scancode_table.
SET1_TO_SDL: dict[tuple[int, bool], int] = {
    (0x01, False): 41, (0x0E, False): 42, (0x0F, False): 43, (0x1C, False): 40,
    (0x39, False): 44, (0x3A, False): 57, (0x2A, False): 225, (0x36, False): 229,
    (0x36, True): 229,  # the LL hook flags Right Shift as extended
    (0x1D, False): 224, (0x1D, True): 228, (0x38, False): 226, (0x38, True): 230,
    (0x5B, True): 227, (0x5C, True): 231, (0x5D, True): 101,
    (0x29, False): 53, (0x0C, False): 45, (0x0D, False): 46, (0x1A, False): 47,
    (0x1B, False): 48, (0x27, False): 51, (0x28, False): 52, (0x2B, False): 49,
    (0x33, False): 54, (0x34, False): 55, (0x35, False): 56, (0x56, False): 100,
    (0x53, True): 76, (0x48, True): 82, (0x50, True): 81, (0x4B, True): 80, (0x4D, True): 79,
    (0x1C, True): 88,
}
for i, sc in enumerate(range(0x02, 0x0B)):
    SET1_TO_SDL[(sc, False)] = 30 + i
SET1_TO_SDL[(0x0B, False)] = 39
for row, sdl_codes in (
    (0x10, (20, 26, 8, 21, 23, 28, 24, 12, 18, 19)),  # q..p
    (0x1E, (4, 22, 7, 9, 10, 11, 13, 14, 15)),  # a..l
    (0x2C, (29, 27, 6, 25, 5, 17, 16)),  # z..m
):
    for i, code in enumerate(sdl_codes):
        SET1_TO_SDL[(row + i, False)] = code
for i in range(10):
    SET1_TO_SDL[(0x3B + i, False)] = 58 + i  # F1..F10
SET1_TO_SDL[(0x57, False)] = 68
SET1_TO_SDL[(0x58, False)] = 69
SDL_TO_SET1 = {v: k for k, v in SET1_TO_SDL.items() if k != (0x36, True)}

S = {
    "is": [
        ("baseline", "Type  a  then  f  then  j , each pressed and released."),
        ("dead+a", "Press the DEAD ACUTE (the key right of Æ), let go, then press  a ."),
        ("dead+e", "Dead acute, then  e ."),
        ("dead+space", "Dead acute, then Space."),
        ("dead twice", "Dead acute, then dead acute again."),
        ("dead+k", "Dead acute, then  k ."),
        ("shift+top-left (¨) +u",
         "Hold Shift, press the TOP-LEFT key (left of 1; with Shift it is the dead ¨), let go of both, then  u ."),
        ("top-left (°) +a", "Press the TOP-LEFT key alone (dead °), let go, then  a ."),
        ("dead, wait, a", "Dead acute. Wait about 3 seconds. Then  a ."),
        ("dead, focus out and back, a",
         "Dead acute. Click into Notepad (type nothing there). Click back into THIS window. Then  a ."),
        ("dead held", "Hold the dead acute down for about 2 seconds, let go. Then  a ."),
        ("FLUSH ON: dead+a x3",
         "Takki-side flush is ON for this step. Three times: dead acute, then  a ."),
        ("FLUSH ON: dead+space, dead+k",
         "Flush still ON. Dead acute then Space. Then dead acute then  k ."),
        ("hold f", "Hold  f  for about 2 seconds, then let go."),
        ("ll released", "Type  l , let go, type  l  again."),
        ("ll held", "Press  l  and hold it about 1.5 seconds, then let go."),
        ("shift released first", "Hold Shift, press  g , let go of Shift FIRST, then let go of  g ."),
        ("focus lost mid-hold",
         "Hold  j . While holding it, click into Notepad with the mouse. Let go of  j  in Notepad. "
         "Click back into THIS window."),
        ("focus gained mid-hold",
         "Click into Notepad. Hold  j  there. While still holding, click back into THIS window. "
         "Let go of  j  here."),
        ("alt+tab out and back", "Press Alt+Tab once (to the previous window), then Alt+Tab back to THIS window."),
        ("keys while unfocused",
         "Click into Notepad. There press: Right Ctrl, then  f , then Escape. Click back into THIS window."),
        ("non-character keys",
         "One at a time, about a second apart, press and release: Enter, Backspace, left Shift, "
         "right Shift, Tab, Caps Lock, Caps Lock again."),
        ("caps lock on", "Caps Lock on. Type  a  then  f . Caps Lock off."),
        ("held non-character keys", "Hold left Shift for 2 seconds, let go. Then hold Enter for 2 seconds, let go."),
        ("fast roll", "Type  fjdk  as fast as you can, three times in a row. Overlapping keys is fine."),
        ("sticky keys",
         "Press left Shift 5 times quickly. If a Sticky Keys dialog opens, choose NO, then click back into "
         "THIS window."),
        ("filter keys",
         "Hold RIGHT Shift for 9 seconds. If a Filter Keys dialog opens, choose NO, then click back into "
         "THIS window."),
    ],
    "de": [
        ("baseline", "Type  a , then the bottom-left letter key (right of left Shift; gives  y  on German)."),
        ("^+e", "Press the  ^  key (top-left, left of 1), let go, then  e ."),
        ("^+space", "^  then Space."),
        ("^ twice", "^  then  ^  again."),
        ("^+k", "^  then  k ."),
        ("´+e", "Press the  ´  key (right of ß, left of Backspace), let go, then  e ."),
        ("`+a", "Hold Shift, press the  ´  key (gives ` ), let go of both, then  a ."),
        ("´+space", "´  then Space."),
        ("´ twice", "´  then  ´  again."),
        ("´+k", "´  then  k ."),
        ("altgr+q", "Hold AltGr (right Alt), press  q  (gives @), let go of both."),
        ("^ held", "Hold the  ^  key for about 2 seconds, let go. Then  e ."),
        ("FLUSH ON: ^+e x3", "Takki-side flush is ON for this step. Three times:  ^  then  e ."),
    ],
    "switch": [
        ("US keys",
         "On English (US). Type four keys: bottom-left letter (US z), the key right of T (US y), "
         "the key right of L (US ;), the key right of that (US ')."),
        ("win+space to German",
         "Hold Win, tap Space until Deutsch is selected, let go of Win. (Watch the layout line above.)"),
        ("German keys", "Type the same four keys again."),
        ("alt+shift", "Press Left Alt + Shift once. Then type the same four keys again."),
        ("back to US", "Switch back to English (US) with Win+Space. Type the same four keys again."),
    ],
    "redo": [
        ("focus lost mid-hold (alt+tab)",
         "First click into Notepad, then click back into THIS window. Now hold  j  with your right hand. "
         "While holding it, press Alt+Tab with your left hand and let go of Alt and Tab, so Notepad comes "
         "forward. Then let go of  j . Then Alt+Tab back to THIS window."),
        ("focus gained mid-hold (alt+tab)",
         "Alt+Tab to Notepad. In Notepad, hold  j . While holding it, Alt+Tab back to THIS window and let go "
         "of Alt and Tab. Then let go of  j  here."),
        ("ll released", "Lower-case L (the key right of K), no Shift: press it, let go, press it again."),
        ("ll held", "Lower-case L, no Shift: press it and hold about 1.5 seconds, then let go."),
        ("drum", "Drum  a s d f  with the four fingers of your left hand, quickly, six or seven times. "
                 "Order does not matter; keys overlapping is the point."),
    ],
    "auto": [("non-character taps", "AUTOMATED: hands off the keyboard and mouse. Enter, Backspace, Tab, Shift.")]
    + [
        step
        for i in (1, 2, 3)
        for step in (
            (f"layout {i}: four keys", "AUTOMATED: the four keys (US z, y, ;, ')."),
            (f"layout {i}: dead-key cases", "AUTOMATED: dead+a, dead+space, dead twice, dead+k."),
            (f"layout {i}: dead, alt+tab out and back, a", "AUTOMATED: three times."),
            (f"FLUSH layout {i}: dead+a x3, dead+space, dead+k", "AUTOMATED: flush on."),
            (f"layout {i}: alt+shift to the next layout", "AUTOMATED: Left Alt + Left Shift."),
        )
    ]
    + [("restore", "AUTOMATED: back to the layout the run started on.")],
    "confirm": [
        ("held dead key x4",
         "Four times: (1) hold the DEAD ACUTE (right of Æ) down - about 1 s the first time, a little longer each "
         "time; (2) let go; (3) press  a  once."),
        ("focus lost mid-hold x2",
         "Twice: (1) hold  j  with your right hand and keep holding; (2) with your left hand press Alt+Tab and "
         "let go of Alt and Tab; (3) let go of  j ; (4) press Alt+Tab to come back to THIS window."),
        ("focus gained mid-hold x2",
         "Twice: (1) click into Notepad; (2) hold  j  there and keep holding; (3) with your left hand press "
         "Alt+Tab to come back to THIS window, let go of Alt and Tab; (4) let go of  j ."),
        ("filter keys",
         "Hold RIGHT Shift down until a Filter Keys box appears (about 8 s), then let go of Shift. "
         "Press Escape to close the box. If THIS window is not in front, click it."),
        ("right ctrl while unfocused",
         "(1) Click into Notepad; (2) press and release RIGHT Ctrl (right of the space bar, past AltGr) "
         "twice; (3) press and release Escape; (4) click back into THIS window."),
    ],
    "window": [
        ("dead+a", "Dead acute (right of Æ), then  a ."),
        ("dead+space", "Dead acute, then Space."),
        ("dead twice", "Dead acute twice."),
        ("dead+k", "Dead acute, then  k ."),
        ("hold f", "Hold  f  for about 2 seconds, then let go."),
        ("ll held", "Press  l  and hold it about 1.5 seconds, then let go."),
        ("fast roll", "Type  fjdk  as fast as you can, three times in a row."),
    ],
}
EXPECTED_LANG = {"is": 0x40F, "de": 0x407, "switch": 0x409, "window": 0x40F, "redo": None, "auto": None, "confirm": 0x40F}

T0 = time.perf_counter()


def now_ms() -> float:
    return round((time.perf_counter() - T0) * 1000.0, 2)


def hkl_of_this_thread() -> str:
    return f"0x{(user32.GetKeyboardLayout(0) or 0):08x}"


class SPIStruct(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwFlags", wt.DWORD)]


class FilterKeys(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("dwFlags", wt.DWORD), ("iWaitMSec", wt.DWORD),
        ("iDelayMSec", wt.DWORD), ("iRepeatMSec", wt.DWORD), ("iBounceMSec", wt.DWORD),
    ]


def accessibility_settings() -> dict[str, object]:
    spi = user32.SystemParametersInfoW
    delay, speed = wt.UINT(), wt.DWORD()
    spi(0x16, 0, ctypes.byref(delay), 0)  # SPI_GETKEYBOARDDELAY: 0..3 -> 250..1000 ms
    spi(0x0A, 0, ctypes.byref(speed), 0)  # SPI_GETKEYBOARDSPEED: 0..31
    sticky = SPIStruct(ctypes.sizeof(SPIStruct), 0)
    spi(0x3A, sticky.cbSize, ctypes.byref(sticky), 0)
    fk = FilterKeys(ctypes.sizeof(FilterKeys))
    spi(0x32, fk.cbSize, ctypes.byref(fk), 0)
    return {
        "keyboard_delay_setting": delay.value,
        "keyboard_delay_ms_nominal": 250 * (delay.value + 1),
        "keyboard_speed_setting": speed.value,
        "stickykeys_flags": hex(sticky.dwFlags),
        "stickykeys_hotkey_active": bool(sticky.dwFlags & 0x4),
        "filterkeys_flags": hex(fk.dwFlags),
        "filterkeys_hotkey_active": bool(fk.dwFlags & 0x4),
    }


def is_dead_key(sdl_scancode: int, hkl: int) -> bool | None:
    set1 = SDL_TO_SET1.get(sdl_scancode)
    if set1 is None:
        return None
    scan, ext = set1
    vk = user32.MapVirtualKeyExW(scan | (0xE000 if ext else 0), 3, hkl)  # MAPVK_VSC_TO_VK_EX
    if not vk:
        return None
    return bool(user32.MapVirtualKeyExW(vk, 2, hkl) & 0x80000000)  # MAPVK_VK_TO_CHAR


def flush_compose_state(hkl: int) -> list[tuple[int, str]]:
    # On the window's own thread: feed Space through ToUnicodeEx with wFlags 0
    # (state may change) until it no longer reports a dead key pending.
    state = (ctypes.c_ubyte * 256)()
    out = []
    for _ in range(3):
        buf = ctypes.create_unicode_buffer(8)
        n = user32.ToUnicodeEx(0x20, 0x39, state, buf, 8, 0, hkl)
        out.append((n, buf.value[: max(n, 0)]))
        if n >= 0:
            break
    return out


SDL_TYPES = {
    0x200: "WINDOW", 0x300: "KEYDOWN", 0x301: "KEYUP", 0x302: "TEXTEDITING",
    0x303: "TEXTINPUT", 0x304: "KEYMAPCHANGED", 0x305: "TEXTEDITING_EXT",
}
WINDOW_EVENTS = {12: "FOCUS_GAINED", 13: "FOCUS_LOST", 1: "SHOWN", 4: "MOVED", 14: "CLOSE", 3: "EXPOSED",
                 10: "ENTER", 11: "LEAVE", 7: "MINIMIZED", 9: "RESTORED", 15: "TAKE_FOCUS"}


def decode_sdl(ptr: int) -> dict[str, object] | None:
    b = ctypes.string_at(ptr, 56)
    typ, ts = struct.unpack_from("<II", b, 0)
    name = SDL_TYPES.get(typ)
    if name is None:
        return None
    rec: dict[str, object] = {"k": "raw", "t": now_ms(), "type": name, "ts": ts}
    if typ in (0x300, 0x301):
        _wid, state, rep = struct.unpack_from("<IBB", b, 8)
        sc, sym, mod = struct.unpack_from("<iiH", b, 16)
        rec.update(sc=sc, sym=sym, mod=mod, rep=rep, state=state)
    elif typ in (0x302, 0x303):
        rec["text"] = b[12:44].split(b"\0")[0].decode("utf-8", "replace")
        if typ == 0x302:
            rec["start"], rec["length"] = struct.unpack_from("<ii", b, 44)
    elif typ == 0x305:
        p = struct.unpack_from("<Q", b, 16)[0]
        rec["text"] = ctypes.string_at(p).decode("utf-8", "replace") if p else None
    elif typ == 0x200:
        ev = struct.unpack_from("<B", b, 12)[0]
        if ev not in WINDOW_EVENTS:
            return None
        rec["wev"] = WINDOW_EVENTS[ev]
    return rec


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in S:
        raise SystemExit(f"usage: {sys.argv[0]} {{{'|'.join(S)}}} [log_path]")
    run = sys.argv[1]
    steps = S[run]
    with_hook = run != "window"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = (
        Path(sys.argv[2]) if len(sys.argv) > 2
        else Path(__file__).parent / "results" / "key_capture_source" / f"{run}-{stamp}.jsonl"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w", encoding="utf-8")

    def write(rec: dict[str, object]) -> None:
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")

    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1100, 520))
    pygame.display.set_caption("Takki key-capture spike")

    sdl = ctypes.CDLL(str(Path(pygame.__file__).parent / "SDL2.dll"))
    sdl.SDL_IsTextInputActive.restype = ctypes.c_int
    text_input_at_start = bool(sdl.SDL_IsTextInputActive())

    raw_records: list[dict[str, object]] = []
    event_filter_t = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    sdl.SDL_GetEventFilter.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
    sdl.SDL_GetEventFilter.restype = ctypes.c_int
    prev_fp, prev_ud = ctypes.c_void_p(), ctypes.c_void_p()
    had_filter = bool(sdl.SDL_GetEventFilter(ctypes.byref(prev_fp), ctypes.byref(prev_ud)))
    prev_filter = event_filter_t(prev_fp.value) if had_filter and prev_fp.value else None

    @event_filter_t
    def raw_filter(_userdata: int, ev: int) -> int:
        rec = decode_sdl(ev)
        if rec is not None:
            raw_records.append(rec)
        return prev_filter(prev_ud.value, ev) if prev_filter is not None else 1

    sdl.SDL_SetEventFilter.argtypes = [event_filter_t, ctypes.c_void_p]
    sdl.SDL_SetEventFilter(raw_filter, prev_ud)

    hook_q: queue.Queue[dict[str, object]] = queue.Queue()
    listener = None
    if with_hook:
        import pynput.keyboard as keyboard

        from takki.input.pynput_stream import translate

        last_ll: dict[str, object] = {}

        def win32_filter(msg: int, data: object) -> bool:
            last_ll.update(
                t=now_ms(), msg=msg, vk=data.vkCode, scan=data.scanCode,  # type: ignore[attr-defined]
                flags=data.flags, ll_time=data.time, hkl_thread=hkl_of_this_thread(),  # type: ignore[attr-defined]
            )
            return True

        def emit(key: object, pressed: bool) -> None:
            if key is None:
                return
            ll = dict(last_ll)
            flags = int(ll.get("flags", 0))
            rec: dict[str, object] = {
                "k": "hook", "dir": "down" if pressed else "up", **ll,
                "ext": bool(flags & 0x01), "inj": bool(flags & 0x10),
                "sdl_sc": SET1_TO_SDL.get((int(ll.get("scan", 0)), bool(flags & 0x01))),
            }
            if isinstance(key, keyboard.KeyCode):
                rec.update(char=key.char, dead=bool(getattr(key, "is_dead", False)), kvk=key.vk)
            else:
                rec.update(name=key.name)  # type: ignore[attr-defined]
            tr = translate(key, pressed)  # type: ignore[arg-type]
            rec.update(tr_char=tr.char, tr_name=tr.name)
            hook_q.put(rec)

        listener = keyboard.Listener(
            on_press=lambda key, injected=False: emit(key, True),
            on_release=lambda key, injected=False: emit(key, False),
            win32_event_filter=win32_filter,
        )
        listener.start()
        listener.wait()

    main_hkl = user32.GetKeyboardLayout(0) or 0
    write({
        "k": "meta", "t": now_ms(), "run": run, "started": datetime.now().isoformat(timespec="milliseconds"),
        "pygame": pygame.version.ver, "sdl": list(pygame.get_sdl_version()), "python": sys.version,
        "hook": with_hook, "had_pygame_filter": had_filter, "text_input_active_at_start": text_input_at_start,
        "main_hkl": f"0x{main_hkl:08x}", **accessibility_settings(),
    })

    font = pygame.font.SysFont("consolas", 22)
    small = pygame.font.SysFont("consolas", 18)
    step = 0
    attempt = 0
    focused_at = -1e9
    typed = ""
    counts = {"hook": 0, "raw": 0}
    dirty = True
    last_draw = 0.0

    def mark_step() -> None:
        nonlocal typed
        typed = ""
        sid, text = steps[step]
        hkl = user32.GetKeyboardLayout(0) or 0
        write({"k": "step", "t": now_ms(), "n": step + 1, "id": sid, "text": text, "attempt": attempt,
               "flush": sid.startswith("FLUSH"), "main_hkl": f"0x{hkl:08x}",
               "text_input_active": bool(sdl.SDL_IsTextInputActive())})

    def wrap(text: str, width: int) -> list[str]:
        lines, cur = [], ""
        for word in text.split(" "):
            trial = f"{cur} {word}" if cur else word
            if font.size(trial)[0] > width and cur:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
        return lines

    def draw() -> None:
        screen.fill((20, 20, 28))
        hkl = user32.GetKeyboardLayout(0) or 0
        lang = hkl & 0xFFFF
        ok = EXPECTED_LANG[run] in (None, lang) or run == "switch" and step > 0
        y = 16
        head = f"run '{run}'  step {step + 1}/{len(steps)}  ({steps[step][0]})"
        screen.blit(small.render(head, True, (160, 200, 255)), (20, y))
        y += 28
        lay = f"layout of this window's thread: 0x{hkl:08x}  (lang 0x{lang:04x})"
        if not ok:
            lay += f"  WRONG: expected 0x{EXPECTED_LANG[run]:04x}. Close, switch, relaunch."
        screen.blit(small.render(lay, True, (120, 230, 120) if ok else (255, 90, 90)), (20, y))
        y += 40
        for line in wrap(steps[step][1], 1050):
            screen.blit(font.render(line, True, (240, 240, 240)), (20, y))
            y += 32
        y += 20
        seen = f"seen this step: hook {counts['hook']}, window {counts['raw']}   window text: {typed!r}"
        screen.blit(small.render(seen, True, (200, 200, 120)), (20, y))
        foot = "Left-click: next step.  Right-click: redo this step.  Close the window when done."
        screen.blit(small.render(foot, True, (140, 140, 140)), (20, 480))
        pygame.display.flip()

    mark_step()
    running = True
    try:
        while running:
            pg_events = pygame.event.get()
            for rec in raw_records:
                write(rec)
                if rec["type"] in ("KEYDOWN", "KEYUP", "TEXTINPUT"):
                    counts["raw"] += 1
                    dirty = True
                if rec.get("wev") == "FOCUS_GAINED":
                    focused_at = time.perf_counter()
            raw_records.clear()
            hkl = user32.GetKeyboardLayout(0) or 0
            for ev in pg_events:
                rec: dict[str, object] = {"k": "pg", "t": now_ms(), "type": pygame.event.event_name(ev.type)}
                if ev.type in (pygame.KEYDOWN, pygame.KEYUP):
                    rec.update(key=ev.key, sc=ev.scancode, uni=getattr(ev, "unicode", None), mod=ev.mod)
                    if ev.type == pygame.KEYDOWN:
                        rec["dead"] = is_dead_key(ev.scancode, hkl)
                elif ev.type in (pygame.TEXTINPUT, pygame.TEXTEDITING):
                    rec["text"] = ev.text
                    if ev.type == pygame.TEXTINPUT:
                        typed += ev.text
                elif ev.type in (pygame.MOUSEMOTION, pygame.WINDOWMOVED, pygame.VIDEOEXPOSE,
                                 pygame.ACTIVEEVENT, pygame.WINDOWEXPOSED):
                    continue
                write(rec)
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN and steps[step][0].startswith("FLUSH") and rec.get("dead"):
                    write({"k": "flush", "t": now_ms(), "sc": ev.scancode, "result": flush_compose_state(hkl)})
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
                    if time.perf_counter() - focused_at < 0.5:
                        write({"k": "note", "t": now_ms(), "text": "click ignored: within 500 ms of focus gain"})
                        continue
                    if ev.button == 1 and step + 1 < len(steps):
                        step += 1
                        attempt = 0
                    elif ev.button == 3:
                        attempt += 1
                    elif ev.button == 1:
                        write({"k": "note", "t": now_ms(), "text": "last step; close the window"})
                        continue
                    counts = {"hook": 0, "raw": 0}
                    mark_step()
                    dirty = True
            while True:
                try:
                    h = hook_q.get_nowait()
                except queue.Empty:
                    break
                write(h)
                counts["hook"] += 1
                dirty = True
            if dirty and time.perf_counter() - last_draw > 0.05:
                draw()
                dirty = False
                last_draw = time.perf_counter()
            time.sleep(0.001)
    finally:
        if listener is not None:
            listener.stop()
            listener.join(2.0)
            while not hook_q.empty():
                write(hook_q.get_nowait())
        write({"k": "end", "t": now_ms()})
        log.close()
        pygame.quit()
        print(f"log: {log_path}")


if __name__ == "__main__":
    main()
