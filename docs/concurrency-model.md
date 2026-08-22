# Takki — Concurrency and Event-Loop Model

> **Status:** Design note — Accepted 2026-08-22 (drafted 2026-07-05 as a design-review follow-up). Sessions 4, 6, and 11 implement against it.
> Part of the [Takki architecture](architecture.md). Grounds [ADR-028](adr/0028-composite-input-and-keyboard-ownership.md) (focus-gated dispatch), [ADR-012](adr/0012-audio-feedback-design.md) (TTS interrupt, sound cues), [ADR-005](adr/0005-keyboard-handling.md) (pynput), and [ADR-019](adr/0019-testing-strategy-and-io-isolation.md) (fakes and testability). Informed by the C12 spike ([research/tts-letter-pronunciation.md](research/tts-letter-pronunciation.md)).

The problem this note settles: Takki combines four things that each bring their own threading story — a pynput listener (callbacks on its own hook thread), a pygame/SDL window whose event pump must run on the main thread, a blocking TTS engine (`pyttsx3.runAndWait()` does not return until the utterance ends), and timers (auto-advance timeout, Escape tap/hold, pace adaptation). Without a declared model, each session invents its own and the engine grows locks. This note declares the model once.

## The model in one paragraph

**The main thread runs a single-threaded event loop that owns all state. Everything else is a producer feeding one thread-safe queue.** The lesson engine, focus state machine, progression logic, and persistence are ordinary single-threaded code that never sees a lock. Exactly two auxiliary threads exist in Alpha (pynput's listener and a TTS worker); each communicates with the core only by putting typed events on the core's inbound queue, and the core communicates with the TTS worker only through a command queue. There is one sanctioned cross-thread call: `TTSEngine.stop()`, validated by the C12 spike.

## Thread inventory (Alpha)

| Thread | Owner / created by | Does | Must never |
|---|---|---|---|
| **Main** | `takki` entrypoint | SDL window + `pygame.event` pump, mixer cue triggering, event dispatch, lesson engine, focus FSM, progression, SQLite writes, timer deadline checks | block (no `sleep`, no `runAndWait`, no joins mid-loop) |
| **pynput listener** | `pynput.keyboard.Listener` | translate raw key event → `KeyEvent` → `inbound_queue.put()` | touch engine state, call pygame, do I/O, block |
| **TTS worker** | `audio` module at startup | own the pyttsx3/SAPI engine exclusively; pop `Speak(text, utterance_id)` commands; `runAndWait()`; post `SpeechFinished(utterance_id, completed | cancelled)` to the inbound queue | be called into from other threads (sole exception: `stop()`) |

Beta adds one more producer of the same shape: a **voice capture worker** (mic frames → `webrtcvad` endpointing → Whisper transcription → `TranscriptReady` event). ADR-030's record mode reuses that worker in a keep/redo loop. Nothing about the model changes; the queue grows new event types.

## The loop

```
while running:
    for ev in pygame.event.get():          # SDL: focus gained/lost, QUIT
        dispatch(translate(ev))
    while (ev := inbound_queue.get_nowait()):   # key events, TTS completions
        dispatch(ev)
    check_deadlines(clock.monotonic())     # auto-advance, Escape hold, pace
    clock.tick(60)                         # ~16 ms/frame ceiling on added latency
```

- **One inbound queue** (`queue.Queue`, unbounded). Every stimulus the core reacts to is a typed event on one stream: `KeyEvent`, `FocusGained`/`FocusLost` (translated from the pygame pump on the main thread — not cross-thread, but normalised into the same dispatch path), `SpeechFinished`, `Quit`. Serialising everything through one stream is what makes the focus FSM and first-attempt accounting race-free by construction.
- **Focus gating happens at dispatch** (ADR-028): while the window is not foreground, `KeyEvent`s are dropped at the top of `dispatch`, before any lesson logic.
- **Latency budget:** at 60 Hz the loop adds ≤ ~16 ms between a keypress and its cue trigger — well inside the "immediate" feel ADR-012 requires. `pygame.mixer.Sound.play()` is non-blocking and fires from the main thread. Tick rate is a compiled default in `config.py` (not parent-facing).

## TTS: the one blocking subsystem

- The worker **owns the engine**; all `say`/`runAndWait` calls happen there. The core requests speech by enqueueing `Speak(text, utterance_id)` and learns the outcome from the `SpeechFinished` event — it never waits.
- **Interrupt on keypress** (ADR-012): the core calls `tts.stop()` directly from the main thread. This is the single cross-thread engine call, and it is exactly what the C12 spike validated on SAPI (a ~12 s utterance cut at ~2.2 s, `stop()` issued from a second thread). The worker's blocked `runAndWait()` returns early and posts `SpeechFinished(cancelled)`.
- Utterance ids keep the core honest: a `SpeechFinished` for a superseded utterance is ignored, so a cancel racing a natural completion cannot double-advance a prompt.
- **Piper (Beta)** slots into the same worker with a different cancel mechanism (stop feeding the audio buffer). The Protocol surface (`speak`, `stop`) doesn't change.

## Timers

No `threading.Timer`, no timer threads. Every timed behaviour — Layer-1 auto-advance, Escape tap/hold discrimination (whichever way that open carry-forward decision lands), pace measurement — is a **deadline field checked each tick** against the `Clock` Protocol's monotonic time. With `FakeClock`, every timeout is unit-testable by setting the time, and the engine stays deterministic.

## Persistence

SQLite stays on the main thread. Per-keystroke `key_attempts` writes are sub-millisecond under WAL + `synchronous=NORMAL` (applied 2026-07-05), so they fit inside the frame budget; keeping the store single-threaded means sqlite3's default same-thread check stays on as a free correctness assertion.

## Shutdown

Signal handlers (delivered to the main thread — another reason the core lives there) set `running = False`. The loop then: enqueues `Shutdown` on the TTS command queue, calls `listener.stop()`, joins workers with a short timeout, and exits. A worker that won't die inside the timeout is abandoned, not waited on forever — the process is exiting anyway.

## Rules for all future code

1. **All mutable lesson/progression/focus state is confined to the main thread.** If a change needs a lock inside `lesson/`, `persistence/`, or the focus FSM, the design is wrong — route it through the queue.
2. **Producer callbacks translate and enqueue, nothing else.** pynput and (Beta) audio-capture callbacks must return in microseconds.
3. **Blocking calls live in worker threads owned by the real implementation** behind its Protocol (ADR-019). No `time.sleep`, `runAndWait`, `join`, or model inference on the main thread.
4. **Cross-thread calls are named or forbidden.** Today the whitelist is exactly `TTSEngine.stop()`. Anything new gets added here explicitly or doesn't happen.
5. **No asyncio.** Every library in the stack (pynput, pygame, pyttsx3, sqlite3, faster-whisper) is callback- or blocking-native; an asyncio scheduler would coexist with these threads without replacing any of them. Rejected as a second concurrency model for zero gain.

## Testability

Default tests never start a thread. The core loop's `dispatch`/`check_deadlines` are driven synchronously: tests feed `KeyEvent`s from `ScriptedKeyStream`, focus transitions from `FakeFocusSource`, time from `FakeClock`, and assert on `FakeTTSEngine`/`FakeSoundCues` recordings. Threads exist only inside real implementations (`PynputKeyStream`, the pyttsx3 worker) and are exercised by the marker-gated tiers (ADR-019).

## Alternatives considered

- **`suppress`-style global capture with engine logic in the pynput callback:** already rejected by ADR-028; additionally it would put lesson state on a foreign thread.
- **asyncio event loop:** rejected — see rule 5.
- **Actor-per-subsystem (thread per module with message passing everywhere):** more threads than problems; the only genuinely blocking Alpha subsystem is TTS.
- **Blocking `queue.get(timeout=…)` instead of a ticked loop:** cannot coexist with the SDL pump, which must be polled on the main thread; the 60 Hz tick serves both.
