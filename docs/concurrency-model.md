# Takki — Concurrency and Event-Loop Model

> **Status:** Design note — Accepted 2026-08-22 (drafted 2026-07-05 as a design-review follow-up). Sessions 4, 6, and 11 implement against it.
> Part of the [Takki architecture](architecture.md). Grounds [ADR-028](adr/0028-composite-input-and-keyboard-ownership.md) (focus-gated dispatch), [ADR-012](adr/0012-audio-feedback-design.md) (TTS interrupt, sound cues), [ADR-005](adr/0005-keyboard-handling.md) (pynput), and [ADR-019](adr/0019-testing-strategy-and-io-isolation.md) (fakes and testability). Informed by the C12 spike ([research/tts-letter-pronunciation.md](research/tts-letter-pronunciation.md)).

The problem this note settles: Takki combines four things that each bring their own threading story — a pynput listener (callbacks on its own hook thread), a pygame/SDL window whose event pump must run on the main thread, a blocking TTS engine (`speak()` does not return until the utterance ends), and timers (auto-advance timeout, Escape tap/hold, pace adaptation). Without a declared model, each session invents its own and the engine grows locks. This note declares the model once.

## The model in one paragraph

**The main thread runs a single-threaded event loop that owns all state. Everything else is a producer feeding one thread-safe queue.** The lesson engine, focus state machine, progression logic, and persistence are ordinary single-threaded code that never sees a lock. Exactly two auxiliary threads exist in Alpha (pynput's listener and a TTS worker); each communicates with the core only by putting typed events on the core's inbound queue, and the core communicates with the TTS worker only through a command queue. There is one sanctioned cross-thread call: `TTSEngine.stop()`, validated by the C12 spike — and since alpha session 12a-2 it makes no COM call at all on Windows, so it costs the caller nothing.

## Thread inventory (Alpha)

| Thread | Owner / created by | Does | Must never |
|---|---|---|---|
| **Main** | `takki` entrypoint | SDL window + `pygame.event` pump, mixer cue triggering, event dispatch, lesson engine, focus FSM, progression, SQLite writes, timer deadline checks | block (no `sleep`, no `runAndWait`, no joins mid-loop) |
| **pynput listener** | `pynput.keyboard.Listener` | translate raw key event → `KeyEvent` → `inbound_queue.put()` | touch engine state, call pygame, do I/O, block |
| **TTS worker** | `audio` module at startup | **construct** (from the factory `get_fallback_tts()` returns) and own the TTS engine exclusively; pop `Speak(text, utterance_id)` commands; speak; post `SpeechFinished(utterance_id, completed | cancelled | failed)` to the inbound queue — **every** command gets one, including when the engine raises | be called into from other threads (sole exception: `stop()`, which on `SapiTTS` only sets a flag); **have its engine handed to it from another thread** |

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

- **One inbound queue** (`queue.Queue`, unbounded). Unbounded is a requirement, not a default: the pynput callback runs inside a Windows `WH_KEYBOARD_LL` hook, and blocking past the OS hook timeout gets the hook silently unregistered. A bounded `put()` that ever waits would take keyboard input down with it (session 5). Every stimulus the core reacts to is a typed event on one stream: `KeyEvent`, `FocusGained`/`FocusLost` (translated from the pygame pump on the main thread — not cross-thread, but normalised into the same dispatch path), `SpeechFinished`, `Quit`. Serialising everything through one stream is what makes the focus FSM and first-attempt accounting race-free by construction.
- **Focus gating happens at dispatch** (ADR-028): while the window is not foreground, `KeyEvent`s are dropped at the top of `dispatch`, before any lesson logic.
- **Latency budget:** at 60 Hz the loop adds ≤ ~16 ms between a keypress and its cue trigger — well inside the "immediate" feel ADR-012 requires. `pygame.mixer.Sound.play()` is non-blocking and fires from the main thread. Tick rate is a compiled default in `config.py` (not parent-facing).
- **The frame wait is its own Protocol** (`FrameLimiter`, `takki/clock.py`, alpha session 11), not a method on `Clock`: the two answer different questions — a clock is queried, a limiter is waited on — and keeping them apart is what lets the default test tier drive ticks by hand and never sleep. `SleepFrameLimiter` is the real one and is the single sanctioned sleep on the main thread; it is not pygame's `Clock`, so the core loop needs no pygame import (ADR-019). Measured 2026-09-10 against the real corpus: the worst in-loop tick over 400 prompts is **~1.5 ms** in both English and German, so the 16 ms budget is not close to binding.
- **`Quit` reaches the core from the SDL pump.** `PygameFocusSource.poll()` translates `pygame.QUIT` onto the same inbound queue, because it is the only thing that sees it and the core loop reaches pygame through no other route (ADR-019). Session 6a left QUIT on the SDL queue "for session 11"; session 11 cannot call `pygame.event.get()`, so the pump forwards it instead. A consumed QUIT counts as an event arriving and suppresses that tick's backup focus poll — a closing window can already read as unfocused, and the `FocusLost` that would otherwise be synthesised reaches the core behind the `Quit` and announces a pause on the way out.

## TTS: the one blocking subsystem

- The worker **owns the engine**; all `say`/`runAndWait` calls happen there. The core requests speech by enqueueing `Speak(text, utterance_id)` and learns the outcome from the `SpeechFinished` event — it never waits.
- **"Owns" starts at construction, not at first use.** An engine built on one thread and spoken from another does not work at all. The mechanism is below, because the one-line version of it is not believable and a reader who does not believe it will undo the fix.
- **Interrupt on keypress** (ADR-012): the core calls `tts.stop()` directly from the main thread. The worker's blocked `speak()` returns early and posts `SpeechFinished(cancelled)`. **Re-measured 2026-09-20 (alpha session 12a-2) against `SapiTTS`, and the earlier figures are superseded: the call now costs the caller 0.000 ms** over 8 samples, because it sets a `threading.Event` and makes no COM call — the purge is issued by the worker on its own thread. The audio stops 0.13–0.36 s after the call, consistently ~0.2 s. *(What it replaced, and a correction: the ~1.17 s on record for pyttsx3 was itself measured against a **truncated** engine, so it overstated the gap. Repaired — see [ADR-003 § The pyttsx3 path was made to work first](adr/0003-text-to-speech.md) — pyttsx3's `stop()` blocks the caller 94–156 ms. The honest comparison is 0.000 ms against ~100 ms, not against a second. The cost is a cross-thread COM round trip serviced by the worker's own message pump; removing the pump removed it. Moving engine ownership back to the main thread remains ruled out — see § The engine belongs to the thread that creates it.)*
- **A single letter costs ~1.36 s of worker time on SAPI** *(re-measured 2026-09-20 at `Rate = 0`, alpha session 12a-2)*: for letters the call time *is* the speech. The first call after construction costs an extra ~2.0 s of driver init. The worker absorbs both and the core never waits, so it is not a budget problem — but it is the floor on how fast Stage 0 can present prompts, and it is ~7× Piper's measured 0.19 s synthesis ([ADR-003](adr/0003-text-to-speech.md)). **Interrupting a letter buys almost nothing**: however early the stop lands, a 1.36 s letter ends at ~1.06–1.17 s. *(This bullet read ~0.94 s until this session, and twice explained it wrongly — first as fixed `runAndWait()` overhead, then as truncation. Truncation was real and is fixed; the remaining difference is the speaking rate, which pyttsx3 set to 2 and `SapiTTS` pins to 0 per ADR-003.)*
- Utterance ids keep the core honest: a `SpeechFinished` for a superseded utterance is ignored, so a cancel racing a natural completion cannot double-advance a prompt.
- ~~**Ids must come from one allocator, and today they do not**~~ — **resolved (2026-09-10, alpha session 11).** Every component that spoke used to mint its own (`SyntheticLetterAudioSource` and `FocusModel` each held a private `itertools.count()` from 0), so on one `TTSWorker` they collided and the filter above discarded live completions or matched stale ones. `TTSWorker.enqueue_speak(text) -> int` now mints the id and returns it, and no caller can choose one. Ids start at 1, so 0 is never live.

- **One object knows what is audible, and it is the core's `Speaker`** (`src/takki/speech.py`, added alpha session 11). It owns the pending sequence, the in-flight id and the interruptible flag, and it is the only thing that calls `TTSWorker.stop()`. This is a correctness requirement, not tidiness: `FocusModel` used to call `TTSWorker.stop()` directly on a focus loss, which cancels the utterance the core is holding an id for — the core then receives `SpeechFinished` for *its own* in-flight id and **advances** the sequence it meant to clear. The gate therefore speaks through `Speaker.announce()` ("say this now, in place of what is audible"), which interrupts and then says. Anything else that grows a voice goes through the same object or reintroduces the same bug.

- **A letter's utterance id is visible to the core.** `LetterAudioSource.play()` returns `int | None` — the id when the source speaks through the shared worker, `None` when it plays its own audio (a Beta clip player). Without it the core cannot tell an outstanding letter from a finished one, so a second letter queues behind the first and the worker plays it after the cue and over the next prompt. Letters are tracked but never *sequenced*: they deliberately do not make the `Speaker` busy, because holding the next prompt until a letter finished would reopen the window where a typed-ahead keystroke lands on no prompt at all.
- **Multi-utterance prompts** are sequenced by the core one at a time, so the command queue never holds a backlog; interrupting therefore clears the core's pending sequence as well as calling `stop()`. **And a `stop()` now also cancels an utterance that is still sitting in the command queue** *(alpha session 12a-2)*: cancellation is a monotonic **id threshold**, `_cancel_through`, not a flag. Everything minted at or before it is cancelled, the worker reports `cancelled` without speaking it at all, and nothing ever clears the threshold. The flag it replaced had to be cleared before each utterance, and every place to clear it left a window where a `stop()` aimed at the command about to be spoken was discarded — which is how a handed-over utterance played in full despite an interrupt, demonstrated as `spoken == ['LINE ONE', 'LINE TWO']` after one `interrupt()`.
- **`Speaker.interrupt()` checks the non-interruptible guard before it stops anything** *(alpha session 12a-2)*. It used to call `self._letters.stop()` first, and for Alpha's `SyntheticLetterAudioSource` that call *is* `TTSWorker.stop()` — so a milestone celebration was cut whenever a letter happened to be outstanding, which is the exact opposite of what the interruptible/non-interruptible split exists for. Pinned by `tests/test_speech.py::TestInterrupt::test_a_non_interruptible_utterance_survives_an_outstanding_letter`, which fails without the reordering. Rules and the interruptible/non-interruptible split are in [ADR-012 § TTS utterance sequencing and cancellation](adr/0012-audio-feedback-design.md#tts-utterance-sequencing-and-cancellation).
- **An engine exception is a `failed` utterance, never a dead worker** *(alpha session 12a-2, 2026-09-24)*. `run_one()` catches around `engine.speak()`, logs, and posts `SpeechFinished(id, "failed")`; a cancel outranks it. A dead worker posts nothing, so the core's `Speaker` would wait forever and the loop would stop issuing prompts — a running app that says nothing. The core treats `failed` exactly like `completed` (`Speaker.on_finished` matches ids, not statuses), so the child loses one utterance, not the session. What the loop should do after *repeated* failures is open ([roadmap § D](roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr)). The machine that has no output at all never gets this far: startup refuses it ([ADR-003](adr/0003-text-to-speech.md), `EXIT_NO_AUDIO`).
- **`cancelled` is unreliable on the Linux dev path** (measured 2026-08-22, alpha session 4 review). pyttsx3's Linux driver initialises espeak with `AUDIO_OUTPUT_RETRIEVAL`, buffers the whole utterance, then plays it inside the synth callback via a blocking `os.system("aplay …")`; `stop()` only sets a flag that `iterate()` consumes, and `iterate()` cannot run while that callback blocks. So a `stop()` on Linux does not cut the audio and `SpeechFinished(status="cancelled")` cannot be trusted there. **This is a pyttsx3 driver limitation, not an espeak-ng one** — the C12 spike drove espeak-ng directly through ctypes and that path cancels correctly. Windows/SAPI, the only distribution target, cancels as specified (C12: a ~12 s utterance cut at ~2.2 s). Do not chase this as a bug on the dev box, and do not write a default-tier test that depends on it.
- **Piper (Beta)** slots into the same worker with a different cancel mechanism (stop feeding the audio buffer). The Protocol surface (`speak`, `stop`) doesn't change.

### SAPI speaks only the first utterance in full

> **Resolved (2026-09-20, alpha session 12a-2). Windows no longer drives SAPI through pyttsx3.**
> The cause turned out to be pyttsx3 purging its own utterance, and the fix was to drop the
> library on Windows rather than work around it — see § The fix: SpVoice, driven directly at the
> end of this section. Everything below is the finding as it stood, kept because the measurements
> are the reason the fix is shaped the way it is.

*(Found 2026-09-20 while measuring the cost of `stop()`. Not previously recorded anywhere, and the most damaging of the TTS findings, because it fails silently and Alpha's commonest utterance is the one shape that hides it.)*

**Reusing one pyttsx3 engine across utterances truncates every utterance after the first to roughly 0.9 seconds of audio.** Measured, all on one worker thread that also built the engine (`spikes/tts_thread_truncation_spike.py truncation`, `audible`, `freshengine`):

| | synthesized length | `speak()` returned |
|---|---|---|
| Long line, **first** utterance on a fresh engine | 4.42 s | 6.34 s (audio + driver init) ✓ |
| Long line, **second** utterance on the same engine | 4.42 s | **0.92 s** ✗ |
| Three long lines in a row on one engine | 13.3 s total | **2.66 s total** ✗ |
| Long line, **fresh engine each time** | 4.42 s | 6.61 s, then 5.36 s ✓ |

The audio is genuinely **cut off**, not merely mis-reported: three lines that are 13.3 s of speech complete in 2.66 s, so the child never hears the remainder.

**Why nothing caught it.** A single letter is 0.90–0.95 s of audio — just under the cutoff. Alpha's overwhelmingly commonest utterance therefore survives intact, and every earlier measurement was taken on letters. An earlier version of the bullet above even recorded the symptom ("near-independent of content") and explained it away as fixed `runAndWait()` overhead.

**What it breaks.** Everything longer than a letter, which in Alpha means the spoken material that matters most: ADR-023's introduction script is ~4.2 s ("New letter F. Use your left index finger…"), so a child would hear *"New letter F. Use your…"* and then silence — for the one utterance in the whole curriculum that teaches rather than tests. Milestone celebrations, the pause/resume announcements and every multi-utterance sequence are affected the same way.

**Cause and the shape of a fix.** This is the same underlying pyttsx3 defect already noted in `FallbackTTS.__init__`: a second `runAndWait()` on one engine misbehaves. Using a fresh `Engine()` instead of `pyttsx3.init()` avoided the *deadlock* that note describes, but not this — the failure merely changed from hanging to truncating. A fresh engine per utterance does speak in full, and costs ~1.3–1.9 s of driver init each time, which is too slow for a prompt loop but may be acceptable for the handful of long utterances. *(Corrected 2026-09-20: that init figure was cold-start contamination. Warm, in one process, a fresh engine per utterance costs ~4.75 s for 4.42 s of audio — almost free. The argument against it was weaker than this sentence claims.)* Alternatives worth measuring before choosing: driving SAPI's `ISpeechVoice` directly through comtypes and skipping pyttsx3's loop entirely (the C12 spike already drove espeak-ng directly by ctypes for the same class of reason), or `startLoop(False)` + `iterate()`. **Alpha session 12a-2 owns this, and it should be measured before the `stop()` question is reopened — every `stop()` figure recorded here was taken against a truncated utterance.**

#### The fix: SpVoice, driven directly

*(2026-09-20, alpha session 12a-2.)*

**The cause is one line of pyttsx3, and it is not subtle once seen.** `DriverProxy._busy` is left
**False** when the first `runAndWait()` returns — the purge's own `EndStream` handler calls
`setBusy(False)` with an empty command queue, and nothing sets it back. So on every later
utterance `engine.say()` runs `driver.say()` **immediately**, outside the loop, and
`runAndWait()` then pumps the `endLoop` command it has just queued — straight away, because
`_busy` is False — whose `driver.stop()` issues `Speak("", SPF_PURGEBEFORESPEAK)` at the
utterance that started microseconds earlier. **The engine cuts its own speech, and it is
self-perpetuating**, because the purge fires an `EndStream` of its own that leaves `_busy` False
again. Runnable: `uv run python spikes/tts_thread_truncation_spike.py busy`.

That also explains the figure that never made sense: the cutoff is not a fixed ~0.9 s. It is
however long SAPI gets between `say()` and the purge, which is why the same experiment measured
0.92 s per line on one run and 2.06 s on another.

**The fix is `takki.audio.sapi_tts.SapiTTS`: `SAPI.SpVoice` driven directly through comtypes, with
no pyttsx3 anywhere on the Windows path.** `FallbackTTS` stays as the Linux dev path and carries a
docstring saying why it must not come back. Four things fall out of the same change:

| | pyttsx3, as shipped | pyttsx3, repaired | SpVoice direct |
|---|---|---|---|
| Utterance after the first | truncated to ~0.9–2.1 s | full length | **full length** |
| Utterance after a *cancel* | — | full only with repair 2 | **full length** |
| `stop()` cost on the caller | — | 94–156 ms | **0.000 ms** over 8 samples |
| OneCore voice id | rejected, `ValueError` swallowed | applies via repair 3 | **applies** (`SpObjectToken.SetId`) |
| COM event sink / message pump | required, and the source of the thread-affinity hang | required | **none** |
| pyttsx3 internals depended on | — | three | **none** |

**The middle column is not hypothetical and it is why this is a judgement rather than a forced move.** pyttsx3 was made to work first: `proxy.setBusy(True)` after each `runAndWait()` fixes truncation, a ~250 ms message pump before that restores the flag the purge's own `EndStream` knocks back down (without it a cancel corrupts the *next* utterance, 2 of 3 lost), and assigning the token onto `proxy._driver._tts.Voice` gets OneCore working. It was rejected because all three lean on undocumented internals and the regression they prevent is **silent** — the property that hid this defect for eleven sessions. Full record, with the `startLoop(False)` + `iterate()` variant and why leaving that loop does *not* stop the audio: [ADR-003 § The pyttsx3 path was made to work first](adr/0003-text-to-speech.md); runnable as `spikes/tts_thread_truncation_spike.py repaired`.

The last row is the one that matters most for this document. Nothing registers for COM events, so
**no thread has to pump a message queue** — which is what made the § below a trap in the first
place. `speak()` calls `Speak(text, SPF_ASYNC)` and then blocks in `WaitUntilDone(10)`, checking a
`threading.Event` between slices; `stop()` **sets that flag and makes no COM call at all**, and the
purge is issued by the worker on its own thread. Audio stops 0.13–0.36 s after the call
(consistently ~0.2 s), which is well inside what ADR-012 asks of an interrupt.

**The worker runs in its own MTA**, not an STA: it blocks in `WaitUntilDone` and never pumps, which
is exactly what an STA thread may not do. One sharp edge came out of building it, and it is worth
recording because it fails loudly but confusingly: **comtypes initialises COM on whichever thread
first imports it, as an STA.** Let that thread be the TTS worker and `CoInitializeEx(MTA)` then
fails with `RPC_E_CHANGED_MODE`. `sapi_tts.py` therefore imports comtypes at module level, under
the `sys.platform` guard, so the import lands on the main thread during startup.

**Every duration recorded in this document above was taken at a faster speaking rate than Takki now
uses.** pyttsx3's SAPI driver set `Rate = 2` for its own 200 wpm default; `SapiTTS` pins `Rate = 0`,
which is what [ADR-003](adr/0003-text-to-speech.md)'s mapping gives for the default `length_scale`
of 1.0. Re-measured at `Rate = 0`: a letter is **1.36 s** (not 0.94 s), ADR-023's introduction
script is **7.42 s** (not ~4.2 s), driver init is ~2.0 s.

### The engine belongs to the thread that creates it

> **Implemented (2026-09-20, alpha session 12a-2).** `PlatformInterface.get_fallback_tts(voice_id)`
> returns a `Callable[[], TTSEngine]` and `TTSWorker` takes that factory, building the engine in
> `build_engine()` as `run()`'s first act. Nothing on the main thread can construct one any more,
> which is the property the rule below actually needs. The mechanism this section describes no
> longer bites on Windows either — `SapiTTS` registers no COM event sink, so there is no completion
> event to mis-deliver — but the rule stands for any future blocking engine on this worker.

*(Written up 2026-09-20 after the first hand-run of the `audio` tier on Windows failed. An earlier version of this section asserted "SAPI5 is COM and the apartment binds at construction", which is the conclusion rather than the mechanism, and was not followable. This is the mechanism, and it is worth the space: it is the single reason Takki would have shipped mute.)*

**`runAndWait()` does not block on speech.** That is the fact everything else follows from, and the name actively hides it. Reading pyttsx3's SAPI driver, `say()` hands the text to SAPI and returns immediately; SAPI speaks in the background and, when it finishes, **fires an event**. `runAndWait()` is a polling loop waiting for that event:

```python
def startLoop(self):
    self._looping = True
    while self._looping:
        pythoncom.PumpWaitingMessages()   # drains THIS thread's message queue
        time.sleep(0.05)
```

So "did the utterance finish?" really means "was the finished-event delivered and dispatched?"

**Delivery is fixed at construction.** The driver's `__init__` creates the COM object and registers an event sink on it. COM delivers those events as window messages **to the message queue of the thread that created the object**, and that binding never moves. `PumpWaitingMessages()` drains only the *calling* thread's queue. Put the two together:

| | creates the object | pumps messages | outcome |
|---|---|---|---|
| **What `main.py` does today** | main thread | TTS worker | event lands in main's queue; the worker pumps its own empty queue **forever** |
| **What it must do** | TTS worker | TTS worker | event lands in the queue being pumped |

The worker is not deadlocked on a lock. It is waiting at a mailbox the letter was never delivered to.

**Demonstrated, 2026-09-20.** An engine built on the main thread and spoken from a worker was still unfinished after 4 s. The main thread then began calling `PumpWaitingMessages()` in a loop, and the worker's utterance completed **0.06 s later** — because main finally drained the queue the event had been sitting in the whole time. Nothing about the worker changed. That is the proof the problem is delivery, not blocking, and it is the experiment to re-run if anyone doubts this section: `uv run python spikes/tts_thread_truncation_spike.py pump`.

**In Takki it hangs forever, not merely slowly.** Nothing rescues it: the main thread runs the 60 Hz loop above — pygame pump, inbound queue, deadlines — and never calls `PumpWaitingMessages()`. The first utterance never completes, no `SpeechFinished` is ever posted, and the child hears silence with no error anywhere.

**Why eleven green sessions went past it.** `FakeTTSEngine` appends to a list, and pyttsx3's Linux espeak driver is a plain shared-library call: neither has an event sink or a message queue, so on the dev box and in every default-tier test any thread may call any engine. The only test that builds a real engine and drives it from a real thread is `tests/test_fallback_tts.py::TestTTSWorkerWithRealEngine::test_real_thread_start_and_join`, it carries the `audio` marker, and no CI job has ever run that marker ([ADR-019 § Headless audio/video](adr/0019-testing-strategy-and-io-isolation.md)). No fake could have modelled this, which is the general lesson: a fake cannot stand in for thread affinity.

**This also explains why `stop()` works and is slow.** With the engine on the worker, a `stop()` from the main thread is the same kind of cross-thread call — but the worker is *inside* `startLoop()`, actively pumping, so the call is serviced rather than lost. The ~1.17 s measured above is the round trip plus that `time.sleep(0.05)` granularity plus SAPI's purge — though see the correction in § TTS: that figure was taken against a truncated engine and the repaired cost is 94–156 ms. One direction works slowly because the receiving thread pumps; the other hangs forever because it does not. Same mechanism, opposite outcomes — and a reason not to "fix" the slow `stop()` by moving engine ownership back to main.

**The rule.** The thread that pumps an engine's messages must be the thread that created it. Concretely: **`get_fallback_tts()` must hand the worker a way to *build* an engine, not a built one** — the worker constructs it as its first act. Any future blocking engine on this worker inherits the rule; Piper (Beta) does not use COM events, but the rule costs nothing there and keeps one shape. Alpha session 12a-2 owns the change, and it is the same change that applies the verified voice id ([ADR-003](adr/0003-text-to-speech.md)), so the two land together.

## Timers

No `threading.Timer`, no timer threads. Every timed behaviour — Layer-1 auto-advance, Escape tap/hold discrimination (whichever way that open carry-forward decision lands), pace measurement — is a **deadline field checked each tick** against the `Clock` Protocol's monotonic time. With `FakeClock`, every timeout is unit-testable by setting the time, and the engine stays deterministic.

## Persistence

SQLite stays on the main thread. Per-keystroke `key_attempts` writes are sub-millisecond under WAL + `synchronous=NORMAL` (applied 2026-07-05), so they fit inside the frame budget; keeping the store single-threaded means sqlite3's default same-thread check stays on as a free correctness assertion.

## Startup

**One-time work that would blow the frame budget happens before the loop starts, never lazily on first use inside it.** If a value is expensive and derivable, derive it during startup and let the loop only read it; if it is expensive and genuinely unavoidable at runtime, it belongs on a worker thread with the result delivered back as an event.

Alpha's case is the language layer. `WordfreqSource` ([ADR-007](adr/0007-language-data-word-frequency.md), landed alpha session 3) caches its two full-corpus scans — grapheme weights and bigram weights — per layout, so warm calls cost microseconds. The **cold** build does not: measured 2026-08-22 on the Celeron G555 dev box, ~767 ms for English (321,180-word corpus) and ~1,977 ms for German. `bigrams()` generates drill content and is therefore called from inside the loop, so a lazy first call would stall it for most of a second — roughly 50× the 16 ms budget. Warm both tables for the profile's language before entering the loop.

**Those figures are per table, and the loop needs both** *(measured 2026-09-10, alpha session 11, same box).* `takki.language.warm()` forces both scans and costs **~1,383 ms (en) / ~3,936 ms (de)**; loading the `wordfreq` corpus itself is a further ~144 ms / ~354 ms, and a second `warm()` costs 0.03 ms. So the real one-time bill is roughly double what the paragraph above records, and the argument for doing it before the loop is correspondingly stronger. A third derived value is read from inside the loop and is easy to miss: `letter_ranking()` is re-derived on **every introduction step**, but it is `grapheme_weights()` plus a sort over ~26 entries, so warming the two tables covers it.

The same rule covers every other one-time cost as it arrives: sound-cue tone generation, and in Beta the Piper model load (~2.3 s, [ADR-003](adr/0003-text-to-speech.md)) and the Whisper model load ([ADR-002](adr/0002-speech-recognition.md)).

**TTS engine construction is the exception, and this paragraph used to list it as an example** *(corrected 2026-09-20, pre-alpha-session-12a review; implemented the same day by 12a-2, which made the exception structural — `get_fallback_tts()` hands back a `Callable[[], TTSEngine]`, so there is no longer an engine for startup to construct even by mistake)*. It is one-time and expensive — 2.25 s for the first utterance on SAPI, most of it driver init — so the rule above says do it at startup, and doing it at startup on the main thread is what deadlocks the worker (§ TTS). The rule's second clause is the one that applies: a cost that is unavoidable off the main thread "belongs on a worker thread with the result delivered back as an event." So the worker builds its own engine as its first act and the startup sequence's job is to *start the worker early*, not to construct the engine for it. Nothing is gained by warming it on the main thread and the app loses its voice entirely.

Ownership of the sequence belongs to the entrypoint, not to each component: `PygameMixerCues` currently calls `pygame.mixer.init()` from its own constructor, which is fine while it is the only pygame consumer but needs sequencing against `pygame.display` init ([ADR-028](adr/0028-composite-input-and-keyboard-ownership.md)) once session 11 creates both.

Note that ADR-007's "letter frequency ranking: sub-100ms for any language" was not reproducible on the dev box (~620 ms for the ranking alone). The figure is hardware-dependent in a way that ADR does not state, which is a further reason not to let any of this happen lazily.

## Shutdown

Signal handlers (delivered to the main thread — another reason the core lives there) set `running = False`. The loop then: enqueues `Shutdown` on the TTS command queue, calls `listener.stop()`, joins workers with a short timeout, and exits. A worker that won't die inside the timeout is abandoned, not waited on forever — the process is exiting anyway.

`stop()` is reachable through the `KeyEventStream` Protocol; `join()` is not — that surface is `start`/`stop` only (session 5), so the wiring holds the concrete stream to join it. Joining is also the only place a dead listener becomes visible: pynput stops the listener and re-raises a callback exception at `join()`, so an unjoined listener that died mid-run is indistinguishable from an idle one — the keyboard just stops responding, with nothing logged.

## Rules for all future code

1. **All mutable lesson/progression/focus state is confined to the main thread.** If a change needs a lock inside `lesson/`, `persistence/`, or the focus FSM, the design is wrong — route it through the queue.
2. **Producer callbacks translate and enqueue, nothing else.** pynput and (Beta) audio-capture callbacks must return in microseconds.
3. **Blocking calls live in worker threads owned by the real implementation** behind its Protocol (ADR-019). No `time.sleep`, `runAndWait`, `join`, or model inference on the main thread.
4. **Cross-thread calls are named or forbidden.** Today the whitelist is exactly `TTSEngine.stop()`. Anything new gets added here explicitly or doesn't happen. Two amendments from the 2026-09-20 review: a whitelisted call must have its **cost on the calling thread** measured, not just its effect (`stop()` was recorded as holding the main thread ~1.17 s on pyttsx3, which nobody had checked — and the figure was itself wrong, see § TTS); and **object construction is a cross-thread act too** — handing a worker an object built elsewhere is the same violation as calling into it, and on COM it is the more expensive one, because it fails silently at the first use rather than at the hand-off. *(Both are now enforced rather than asked for, alpha session 12a-2: `get_fallback_tts()` returns a factory so construction cannot happen off the worker, and the one whitelisted call reaches no COM object at all — `SapiTTS.stop()` sets a `threading.Event` and the worker issues the purge itself. The whitelist stays non-empty because `FallbackTTS` on the Linux dev path still calls into pyttsx3.)*
5. **No asyncio.** Every library in the stack (pynput, pygame, pyttsx3, sqlite3, faster-whisper) is callback- or blocking-native; an asyncio scheduler would coexist with these threads without replacing any of them. Rejected as a second concurrency model for zero gain.

## Testability

Default tests never start a thread. The core loop's `dispatch`/`check_deadlines` are driven synchronously: tests feed `KeyEvent`s from `ScriptedKeyStream`, focus transitions from `FakeFocusSource`, time from `FakeClock`, and assert on `FakeTTSEngine`/`FakeSoundCues` recordings. Threads exist only inside real implementations (`PynputKeyStream`, the pyttsx3 worker) and are exercised by the marker-gated tiers (ADR-019).

## Alternatives considered

- **`suppress`-style global capture with engine logic in the pynput callback:** already rejected by ADR-028; additionally it would put lesson state on a foreign thread.
- **asyncio event loop:** rejected — see rule 5.
- **Actor-per-subsystem (thread per module with message passing everywhere):** more threads than problems; the only genuinely blocking Alpha subsystem is TTS.
- **Blocking `queue.get(timeout=…)` instead of a ticked loop:** cannot coexist with the SDL pump, which must be polled on the main thread; the 60 Hz tick serves both.
