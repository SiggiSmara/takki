"""
Spike: pynput reality — composite keys, keyboard ownership, keypress taxonomy

Resolves corner cases logged in docs/roadmap.md:

  B5  Dead-key / AltGr observability. ADR-005 says "dead keys and AltGr are
      handled by Windows before the app sees them," but ADR-023/024 want to
      introduce and DRILL the dead-key / AltGr modifier as its own key. What does
      pynput actually deliver for: a dead-key press, then a base letter (does 'á'
      arrive as one event? does the dead key surface at all? does the pending
      compose state leak into the NEXT keypress?), and for AltGr chords?

  C8  Keyboard ownership. With the visual display off (the default) Takki may have
      no focused window. pynput's listener is a GLOBAL hook — do the child's
      keystrokes leak into whatever app is focused? Does the Windows key steal
      focus? Does suppress=True swallow input cleanly (and safely)?

  Keypress taxonomy. What do Backspace / Enter / Tab / Win / arrows / function
  keys look like, so the engine can classify each as accept / error / boundary /
  swallow.

This spike is INTERACTIVE and Windows-only. It prints a scenario, you perform the
keypresses, and it logs the raw pynput events. Advance each scenario by pressing
Enter in this console.

Run from repo root on the Windows laptop:
    uv run python spikes/pynput_reality_spike.py

The suppression test (C8 phase 2) is OPT-IN and risky — it swallows all keyboard
input system-wide for a few seconds. It only runs if you pass --suppress, and it
auto-stops after a fixed timeout so you are never trapped:
    uv run python spikes/pynput_reality_spike.py --suppress

To exercise B5 you must switch the Windows keyboard layout first (see scenarios):
  - dead-key acute: add "United States-International" or an Icelandic layout
  - AltGr letters:  add a "Polish (Programmers)" layout (AltGr+a = ą)
Switch layouts with Win+Space (or Alt+Shift), then come back to this console.

Paste the full stdout back into the Claude Code session.
"""

import sys
import time

try:
    from pynput import keyboard
except ImportError:
    print("FAIL: pynput not importable. This spike is Windows-only "
          "(pynput is pinned to win32 in pyproject). Run it on the laptop.")
    sys.exit(1)

_t0 = time.perf_counter()


def fmt_event(kind: str, key) -> str:
    char = getattr(key, "char", None)
    vk = getattr(key, "vk", None)
    name = getattr(key, "name", None)  # special keys (Key.ctrl_r etc.)
    parts = [f"[{time.perf_counter() - _t0:7.3f}s]", f"{kind:7s}", f"repr={key!r}"]
    if char is not None:
        parts.append(f"char={char!r}")
    if name is not None:
        parts.append(f"name={name}")
    if vk is not None:
        parts.append(f"vk={vk}")
    return "  ".join(parts)


def on_press(key) -> None:
    print(fmt_event("PRESS", key))


def on_release(key) -> None:
    print(fmt_event("RELEASE", key))


def section(title: str) -> None:
    print(f"\n{'=' * 66}\n  {title}\n{'=' * 66}")


def scenario(n: int, title: str, instructions: list[str]) -> None:
    section(f"Scenario {n}: {title}")
    for line in instructions:
        print(f"  - {line}")
    input("\n  >>> Do the above, watch the events, then press Enter to continue...\n")


def run_observation_scenarios() -> None:
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    print("\nGlobal listener started (suppress=False). Events print as you type.")
    print("Keys ALSO go to whatever window is focused — keep THIS console focused")
    print("except where a scenario tells you otherwise.\n")

    scenario(1, "Plain letters (baseline)", [
        "Type: a  s  d  (the home-row letters).",
        "Expect: PRESS/RELEASE with char='a' etc. Confirm char is populated.",
    ])
    scenario(2, "The push-to-talk key (ADR-020)", [
        "Press and release the RIGHT Ctrl key once.",
        "Expect: a Key.ctrl_r event with a vk, distinguishable from left Ctrl.",
        "Then press LEFT Ctrl once so we can compare the two.",
    ])
    scenario(3, "Dead-key acute (B5) — layout switch required", [
        "Switch to 'United States-International' or an Icelandic layout (Win+Space).",
        "Type the acute/dead key (apostrophe on US-Intl), THEN the letter a.",
        "Watch closely: does the dead key produce ANY event? Does 'a' arrive as",
        "  char='á' (one composed event) or as char='a'?",
        "Now press the dead key, then SPACE (should give a literal ' acute).",
        "Then type a NORMAL letter (e.g. s) immediately after a lone dead-key press",
        "  to see whether a pending accent LEAKS onto it.",
    ])
    scenario(4, "AltGr chord (B5) — Polish layout", [
        "Switch to 'Polish (Programmers)' layout (Win+Space).",
        "Press AltGr + a  (should produce ą).",
        "Watch: does AltGr show up as its own event (and/or as Ctrl+Alt)?",
        "Does ą arrive as one event with char='ą', or as separate pieces?",
        "Then press AltGr alone (no letter) and release — what, if anything, fires?",
    ])
    scenario(5, "Keypress taxonomy", [
        "Switch back to your normal layout. Press each once, slowly:",
        "Backspace, Enter, Tab, Esc, Left-Arrow, F1, CapsLock, and the Windows key.",
        "Note for each: does it arrive as Key.<name>? does the Windows key open the",
        "  Start menu (i.e. steal focus from this console)?",
    ])

    listener.stop()
    print("\nObservation listener stopped.")


def run_leak_test() -> None:
    section("Scenario 6: Focus leak (C8) — non-suppressing")
    print("  With the listener running (suppress=False), open Notepad NOW and click")
    print("  into it. Type: leak test")
    print("  The events will STILL appear in this console (global hook), AND the text")
    print("  should appear in Notepad — that is the leak we care about with display off.")
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    input("\n  >>> Type into Notepad, observe, then press Enter here to continue...\n")
    listener.stop()
    print("  Report: did 'leak test' appear in Notepad? (Expected: yes.)")


def run_suppress_test(timeout_s: int = 12) -> None:
    section("Scenario 7: Suppression (C8) — OPT-IN, swallows all keys")
    print(f"  A suppress=True listener will run for {timeout_s} seconds. While it runs,")
    print("  ALL keyboard input is swallowed system-wide — no app receives keys.")
    print("  Have Notepad open and focused BEFORE the countdown ends.")
    print("  Try to type into Notepad during the window: if suppression works, Notepad")
    print("  receives NOTHING and only this console logs events.")
    print(f"  The listener auto-stops after {timeout_s}s, returning keyboard to normal.")
    for s in range(5, 0, -1):
        print(f"    starting in {s}...", flush=True)
        time.sleep(1)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release, suppress=True)
    listener.start()
    time.sleep(timeout_s)
    listener.stop()
    print(f"\n  Suppression window closed. Keyboard back to normal.")
    print("  Report: did any keys reach Notepad during the window? (Expected: no.)")


def main() -> None:
    print("pynput Reality Spike")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")
    if sys.platform != "win32":
        print("\nWARNING: not on win32. Results will not reflect the Windows compose")
        print("model that ADR-005/023 depend on. Run this on the laptop.\n")

    run_observation_scenarios()
    run_leak_test()

    if "--suppress" in sys.argv:
        run_suppress_test()
    else:
        section("Scenario 7 skipped (pass --suppress to run the suppression test)")
        print("  The suppression test swallows all keyboard input for a few seconds.")
        print("  Re-run with --suppress when you are ready and have Notepad open.")

    section("DONE")
    print("  Paste the full stdout back to Claude, and add short notes for the")
    print("  by-eye questions (dead-key leak? Notepad leak? Win key stole focus?).")


if __name__ == "__main__":
    main()
