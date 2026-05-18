# ADR-016: Visual Display Design

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Optional secondary visual display, off by default, child-configured. Consistent two-line layout across both lesson layers. Visual cues appear after or simultaneously with audio — never before. Display shows only what is directly part of the current task.

### Rationale

Literature on learned helplessness in visually impaired children establishes that over-assistance from observers who have more information than the child is a documented harm. A visual display that surfaces per-keypress error data to an observer before the child has processed their own audio feedback creates exactly the information asymmetry that produces this effect. VI children themselves report feeling their independence limited by parents and support teachers who intervene on the basis of what they observe.

The governing principle is the **observer invariant**: nothing appears on screen during a session that the child has not already heard or is simultaneously hearing. The screen is a subtitle to the audio, not an additional information channel.

The display is opt-in and child-controlled — consistent with the finding that true independence means control over how and when support is received. Children with visual impairments typically know their preferred colors and contrast settings from other assistive tools; the setup workflow respects this prior knowledge.

### The Two-Line Layout

All visual display uses a consistent two-line structure:

- **Upper line** — the prompt: what the child is supposed to type
- **Lower line** — the response: what the child has typed, with the cursor marking the current position

**Layer 1 (character drills):**

```
        a              ← current target character, centered
    f g h |            ← up to 3 history characters left of centered cursor
```

- Upper line: current target character, large, centered. Appears simultaneously with TTS announcement.
- Lower line: up to 3 most recently correctly typed characters to the left of a centered cursor. Cursor sits directly below the target character in the upper line.
- On correct keypress: the correct character briefly occupies the cursor position, shifts left into history, oldest history character disappears off-screen, upper line updates to the next target.
- On wrong keypress: nothing changes. Cursor stays. Upper line stays. No error indicator of any kind.

**Layer 2 (real words):**

```
h o u s e             ← full word
h o u | _             ← typed characters aligned, cursor at next position
```

- Upper line: the full word, displayed from the start.
- Lower line: correctly typed characters aligned character-by-character with the upper line. Cursor at the next untyped position, directly below the corresponding character above.
- On correct keypress: character fills cursor position, cursor advances one step right.
- On wrong keypress: nothing changes. No error indicator.

### What the Display Never Shows

- Error indicators — no red X, no color change, no flash on wrong keypress
- What wrong key was pressed
- Real-time accuracy statistics or WPM
- A keyboard diagram or key highlighting
- Running session statistics
- Layer or mode indicator during a session
- Vocabulary coverage percentage during a session

All of the above are either available post-session in the parent/teacher summary (ADR-014) or serve only as observer-facing data that creates information asymmetry.

### Visual Setup Workflow

Setup is navigated entirely by audio. The child runs through five steps:

1. **On/off** — visual display is off by default. The child explicitly enables it.
2. **Text size** — named steps: Large, Very Large, Maximum. TTS names each; a sample character previews on screen.
3. **Background color** — see Color Selection below.
4. **Foreground color** — same flow; the chosen background is shown throughout so the child previews the actual combination as foreground changes.
5. **Cursor style** — Block, Underline, Blinking. TTS names each; cursor updates live in the preview.

After all five steps, the full combination is shown with a sample word:

> TTS: *"Here is how your screen will look — yellow background, black text, showing the word 'house'. Press Enter to save or Escape to change."*

Settings are stored per child profile in SQLite (see ADR-011).

### Color Selection

Children with visual impairments typically know their preferred colors from overlays and assistive tools used in school. The selection flow respects this prior knowledge:

1. TTS asks the child to name their preferred color.
2. `faster-whisper` transcribes the response. A fuzzy match is attempted against the palette and common synonyms (e.g. "navy" / "dark blue" → Navy; "ivory" / "off-white" → Cream).
3. If a match is found: the screen previews the color immediately. TTS confirms and asks the child to accept or try again.
4. If no match or no response: TTS moves to browse mode — each palette color is spoken in turn, the screen updates live, and the child confirms with Enter or voice.

Background is selected first, then foreground. The chosen background is shown throughout foreground selection so the child always previews the real combination.

**Palette:**

| Name | Hex |
|---|---|
| Black | #000000 |
| White | #FFFFFF |
| Yellow | #FFE600 |
| Orange | #FF6600 |
| Red | #CC0000 |
| Blue | #0055CC |
| Green | #008800 |
| Purple | #6600CC |
| Cream | #FFFACD |
| Navy | #001F5B |

Foreground and background are chosen independently. The only constraint: foreground and background may not be the same color — same-color entries are excluded from the browse list and rejected on voice match. No soft warning for near-similar colors — the live preview gives the child direct feedback on readability and they are the best judge of their own vision.

### Alternatives Considered

- **Pre-paired high-contrast presets:** Rejected. VI children's visual needs vary significantly by condition; free independent selection with a live preview respects individual needs and prior knowledge.
- **Real-time error indicators (red X, color flash):** Rejected. Creates information asymmetry — an observer sees error data before the child has processed their own audio feedback. Literature links this directly to learned helplessness in VI children.
- **Keyboard diagram with key highlighting:** Rejected. Undermines the touch-typing goal; creates a visual dependency that delays muscle memory formation.
- **Single-line display:** Rejected. Conflates prompt and response; requires a different layout metaphor for Layer 1 vs Layer 2, creating unnecessary cognitive overhead at the layer transition.
- **Observer-facing real-time dashboard:** Rejected. All observer data is post-session via the parent/teacher summary (ADR-014). Real-time observer data creates conditions for unsolicited intervention.
